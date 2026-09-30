#!/usr/bin/env python3
"""
Historical collection from TheStatsAPI -> data/ginf_api.csv + data/events_api.csv.

Those CSVs feed training/import_historical_events.py (run.py historical).

    python -u collectors/backfill_thestatsapi.py                    # all leagues, 2020 → now
    python -u collectors/backfill_thestatsapi.py --league "Premier League" --year 2024
    python -u collectors/backfill_thestatsapi.py --max-matches 500  # cap calls per run
    python -u collectors/backfill_thestatsapi.py --probe            # print raw API shapes (1 league)

Resumable: matches already in ginf_api.csv (or data/thestatsapi_skipped.csv)
are never fetched again, so a run cut short by the daily quota picks up where
it stopped. Exit codes: 0 complete, 3 stopped early (quota / --max-matches).

A match is only written when its goal timeline adds up to the final score —
a partial timeline would corrupt 2-up / turnaround profiles. Mismatches go to
data/thestatsapi_skipped.csv (retry with --retry-skipped).
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collectors import thestatsapi as ts
from constants import SUPPORTED_LEAGUES
from team_normalizer import normalize_team

FIRST_YEAR = 2020
EXIT_PARTIAL = 3
DATA_DIR = PROJECT_ROOT / "data"
GINF_API = DATA_DIR / "ginf_api.csv"
EVENTS_API = DATA_DIR / "events_api.csv"
SKIPPED = DATA_DIR / "thestatsapi_skipped.csv"
GINF_FIELDS = ["id_odsp", "date", "league", "season", "country", "ht", "at", "fthg", "ftag", "odd_h", "odd_d", "odd_a"]
EVENT_FIELDS = ["id_odsp", "time", "event_type", "event_type2", "side", "event_team", "player", "is_goal", "situation"]
SKIPPED_FIELDS = ["id_odsp", "league", "season", "reason", "at"]


def default_years():
    return list(range(FIRST_YEAR, datetime.now(timezone.utc).year + 1))


def existing_ids(path):
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {row.get("id_odsp", "") for row in csv.DictReader(handle)}


def append_rows(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


_seasons_cache = {}


def seasons_for(competition_id):
    if competition_id not in _seasons_cache:
        payload = ts.api_get(f"/football/competitions/{competition_id}/seasons")
        rows = ts.unwrap(payload) or []
        if isinstance(rows, dict):
            rows = [rows]
        _seasons_cache[competition_id] = rows
    return _seasons_cache[competition_id]


def season_id_for_year(competition_id, year):
    year_s = str(year)
    for row in seasons_for(competition_id):
        name = str(row.get("name") or row.get("season") or row.get("id") or "")
        start = str(row.get("start_year") or row.get("year") or "")
        if start == year_s or name.startswith(year_s) or f"{year_s}/" in name or f"{year_s}-" in name:
            return row.get("id")
    return None


def list_finished(competition_id, season_id):
    matches = []
    page = 1
    while page <= 20:
        payload = ts.api_get(
            "/football/matches",
            {
                "competition_id": competition_id,
                "season_id": season_id,
                "status": "finished",
                "per_page": 100,
                "page": page,
            },
        )
        rows = ts.unwrap(payload) or []
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            break
        matches.extend(rows)
        meta = payload.get("meta") if isinstance(payload, dict) else {}
        total_pages = (meta or {}).get("total_pages") or page
        if page >= total_pages:
            break
        page += 1
    return matches


def timeline_goals(match_id):
    payload = ts.api_get(
        f"/football/matches/{match_id}/timeline",
        {"event_type": "goal"},
    )
    data = ts.unwrap(payload) or {}
    if isinstance(data, dict):
        return data.get("events") or []
    if isinstance(data, list):
        return data
    return []


def side_name(match, key):
    block = match.get(key) or match.get(f"{key}_team") or {}
    if isinstance(block, dict):
        return block.get("name") or ""
    return ""


def side_score(match, key):
    block = match.get(key) or match.get(f"{key}_team") or {}
    if isinstance(block, dict) and block.get("score") is not None:
        return block.get("score")
    score = match.get("score") or {}
    if isinstance(score, dict):
        value = score.get(key)
        if isinstance(value, dict):
            return value.get("fulltime") or value.get("ft")
        return value
    return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def goal_rows(oid, events, home, away):
    """Goal events -> events_api.csv rows. Returns (rows, unmatched_team_count)."""
    rows = []
    unmatched = 0
    for event in events:
        if str(event.get("type") or "").lower() != "goal":
            continue
        team = normalize_team(((event.get("team") or {}).get("name")) or "")
        side = 1 if team == home else 2 if team == away else None
        if side is None:
            unmatched += 1
            continue
        minute = (_as_int(event.get("minute")) or 0) + (_as_int(event.get("extra_time")) or 0)
        player = ((event.get("player") or {}).get("name")) or ""
        rows.append({
            "id_odsp": oid, "time": minute, "event_type": 1,
            "event_type2": "", "side": side, "event_team": team,
            "player": player, "is_goal": 1, "situation": event.get("period") or "",
        })
    return rows, unmatched


def check_match(fthg, ftag, rows, unmatched):
    """None if the timeline is usable, else the reason it is not."""
    if fthg is None or ftag is None:
        return "no_final_score"
    if unmatched:
        return f"goal_team_unmatched:{unmatched}"
    home_goals = sum(1 for r in rows if r["side"] == 1)
    away_goals = sum(1 for r in rows if r["side"] == 2)
    if (home_goals, away_goals) != (fthg, ftag):
        return f"timeline_{home_goals}-{away_goals}_vs_final_{fthg}-{ftag}"
    return None


def probe(league):
    """Print raw response shapes so field names can be checked against the code."""
    def show(label, payload):
        text = json.dumps(payload, indent=2, default=str)
        print(f"\n=== {label} ===\n{text[:2500]}")

    cid = ts.find_competition_id(league)
    if not cid:
        print(f"No competition for {league}")
        return 1
    seasons = seasons_for(cid)
    show(f"seasons for {league} ({cid})", seasons[:5])
    this_year = datetime.now(timezone.utc).year
    sid = season_id_for_year(cid, this_year - 1) or season_id_for_year(cid, this_year - 2)
    if not sid and seasons:
        sid = seasons[-1].get("id")
        print("\n(no season matched by year — check season name/start_year fields above)")
    print(f"\nprobing season id: {sid}")
    if not sid:
        return 1
    matches = list_finished(cid, sid)
    print(f"finished matches: {len(matches)}")
    if not matches:
        return 1
    match = matches[0]
    show("first match", match)
    mid = ts.match_id_of(match)
    events = timeline_goals(mid)
    show(f"timeline goals for {mid}", events)
    home = normalize_team(side_name(match, "home"))
    away = normalize_team(side_name(match, "away"))
    fthg, ftag = _as_int(side_score(match, "home")), _as_int(side_score(match, "away"))
    rows, unmatched = goal_rows(f"ts-{mid}", events, home, away)
    print(f"\nparsed: {home} {fthg}-{ftag} {away}; goal rows={len(rows)} unmatched={unmatched}")
    print(f"check: {check_match(fthg, ftag, rows, unmatched) or 'OK'}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", action="append", help="Repeatable; default all supported leagues")
    parser.add_argument("--year", type=int, action="append", help="Season start year; repeatable")
    parser.add_argument("--max-matches", type=int, default=0,
                        help="Stop after fetching this many timelines (0 = no cap)")
    parser.add_argument("--retry-skipped", action="store_true",
                        help="Re-fetch matches previously skipped as incomplete")
    parser.add_argument("--probe", action="store_true",
                        help="Print raw API shapes for one league and exit")
    args = parser.parse_args(argv)

    ts.require_key()
    leagues = args.league or list(SUPPORTED_LEAGUES)
    years = args.year or default_years()

    if args.probe:
        return probe(leagues[0])

    seen = existing_ids(GINF_API)
    skipped_before = set() if args.retry_skipped else existing_ids(SKIPPED)
    print(f"Leagues: {len(leagues)}  Years: {years[0]}-{years[-1]}")
    print(f"Already collected: {len(seen)}  previously skipped: {len(skipped_before)}")

    added = goals_n = already = incomplete = failed = fetched = 0
    stopped = None
    try:
        for league in leagues:
            try:
                cid = ts.find_competition_id(league)
            except ts.QuotaExhausted:
                raise
            except Exception as exc:
                print(f"{league}: lookup failed ({exc})")
                continue
            if not cid:
                continue
            for year in years:
                try:
                    sid = season_id_for_year(cid, year)
                    if not sid:
                        print(f"  {league} {year}: no season id")
                        continue
                    matches = list_finished(cid, sid)
                except ts.QuotaExhausted:
                    raise
                except Exception as exc:
                    print(f"  {league} {year}: list failed ({exc})")
                    continue
                todo = [
                    m for m in matches
                    if ts.match_id_of(m)
                    and f"ts-{ts.match_id_of(m)}" not in seen
                    and f"ts-{ts.match_id_of(m)}" not in skipped_before
                ]
                already += len(matches) - len(todo)
                print(f"  {league} {year}/{str(year + 1)[-2:]}: "
                      f"{len(matches)} finished, {len(todo)} new")
                for match in todo:
                    if args.max_matches and fetched >= args.max_matches:
                        stopped = f"--max-matches {args.max_matches} reached"
                        raise StopIteration
                    mid = ts.match_id_of(match)
                    oid = f"ts-{mid}"
                    home = normalize_team(side_name(match, "home"))
                    away = normalize_team(side_name(match, "away"))
                    fthg = _as_int(side_score(match, "home"))
                    ftag = _as_int(side_score(match, "away"))
                    try:
                        events = timeline_goals(mid)
                    except ts.QuotaExhausted:
                        raise
                    except Exception as exc:
                        failed += 1
                        print(f"    timeline failed {mid}: {exc}")
                        continue
                    fetched += 1
                    rows, unmatched = goal_rows(oid, events, home, away)
                    reason = check_match(fthg, ftag, rows, unmatched)
                    if reason:
                        incomplete += 1
                        append_rows(SKIPPED, SKIPPED_FIELDS, [{
                            "id_odsp": oid, "league": league, "season": year,
                            "reason": reason,
                            "at": datetime.now(timezone.utc).isoformat(),
                        }])
                        continue
                    # Events first: a crash between the two writes leaves the
                    # match unrecorded (re-fetched next run), never goal-less.
                    if rows:
                        append_rows(EVENTS_API, EVENT_FIELDS, rows)
                    append_rows(GINF_API, GINF_FIELDS, [{
                        "id_odsp": oid, "date": (ts.kickoff_of(match) or "")[:10],
                        "league": league, "season": str(year), "country": "",
                        "ht": home, "at": away, "fthg": fthg, "ftag": ftag,
                        "odd_h": "", "odd_d": "", "odd_a": "",
                    }])
                    seen.add(oid)
                    added += 1
                    goals_n += len(rows)
    except StopIteration:
        pass
    except ts.QuotaExhausted as exc:
        stopped = f"quota exhausted ({exc})"

    print(f"added {added} matches ({goals_n} goals), already had {already}, "
          f"incomplete {incomplete}, failed {failed}, timelines fetched {fetched}")
    if stopped:
        print(f"Stopped early: {stopped}. Rerun to continue where this left off.")
        return EXIT_PARTIAL
    return 0


if __name__ == "__main__":
    sys.exit(main())
