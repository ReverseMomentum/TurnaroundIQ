#!/usr/bin/env python3
"""
Historical backfill from api-sports.io -> data/ginf_apisports.csv + data/events_apisports.csv.

Default: every league in constants.SUPPORTED_LEAGUE_IDS, the last 5
completed seasons. The in-progress season is left to the live results
collector (it already fetches those matches) unless --include-current.

    python -u collectors/backfill_apisports.py                     # everything, resumes
    python -u collectors/backfill_apisports.py --league-id 39 --season 2024
    python -u collectors/backfill_apisports.py --seasons 3
    python -u collectors/backfill_apisports.py --probe             # 1 league: raw shapes + parse check

Nothing is paid for twice:
  - each league's season list is cached for 7 days (data/apisports_seasons.json)
  - a completed season, once fully collected, is recorded in
    data/apisports_done.csv and never listed again
  - a fixture already stored (or skipped as unusable) is never re-fetched
So once the backfill is complete, a nightly run makes 0 calls (30 once a
week to refresh season lists, which is how a newly finished season is picked up).

First full run: ~30 season lists + 150 fixture lists + 1 call per 20 fixtures
(events come back with /fixtures?ids=) — about 2.5k calls for 30 leagues x 5
seasons. Stops at APISPORTS_RESERVE calls left for the day (exit 3) and
resumes next run.

A match is written only when its goal events reproduce the official full-time
score (missed penalties ignored, own goals resolved). Anything else goes to
data/apisports_skipped.csv (retry with --retry-skipped).
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

from collectors import apisports as af
from constants import SUPPORTED_LEAGUE_IDS
from team_normalizer import normalize_team

DEFAULT_SEASONS = 5
BATCH = 20
EXIT_PARTIAL = 3
DATA_DIR = PROJECT_ROOT / "data"
GINF = DATA_DIR / "ginf_apisports.csv"
EVENTS = DATA_DIR / "events_apisports.csv"
SKIPPED = DATA_DIR / "apisports_skipped.csv"
# Completed past seasons fully collected — not re-listed on later runs.
DONE = DATA_DIR / "apisports_done.csv"
DONE_FIELDS = ["key", "league", "season", "matches", "at"]
SEASONS_CACHE = DATA_DIR / "apisports_seasons.json"
SEASONS_CACHE_DAYS = 7
GINF_FIELDS = ["id_odsp", "date", "league", "season", "country", "ht", "at", "fthg", "ftag", "odd_h", "odd_d", "odd_a"]
EVENT_FIELDS = ["id_odsp", "time", "event_type", "event_type2", "side", "event_team", "player", "is_goal", "situation"]
SKIPPED_FIELDS = ["id_odsp", "league", "season", "reason", "at"]


def existing_ids(path):
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {row.get("id_odsp", "") for row in csv.DictReader(handle)}


def append_rows(path, fields, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


# --- API calls ---------------------------------------------------------------

def _load_seasons_cache():
    try:
        return json.loads(SEASONS_CACHE.read_text())
    except (OSError, ValueError):
        return {}


def league_seasons(league_id, refresh=False):
    """[{year, current, events_covered}] newest first; cached for SEASONS_CACHE_DAYS."""
    cache = _load_seasons_cache()
    entry = cache.get(str(league_id))
    if entry and not refresh:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(entry["at"])
            if age.days < SEASONS_CACHE_DAYS:
                return entry["seasons"]
        except (KeyError, ValueError):
            pass
    seasons = _fetch_league_seasons(league_id)
    if seasons:
        cache[str(league_id)] = {
            "at": datetime.now(timezone.utc).isoformat(), "seasons": seasons,
        }
        SEASONS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SEASONS_CACHE.write_text(json.dumps(cache, indent=1))
    return seasons


def _fetch_league_seasons(league_id):
    payload = af.api_get("/leagues", {"id": league_id})
    rows = payload.get("response") or []
    if not rows:
        return []
    out = []
    for s in rows[0].get("seasons") or []:
        cov = ((s.get("coverage") or {}).get("fixtures") or {})
        out.append({
            "year": s.get("year"),
            "current": bool(s.get("current")),
            "events_covered": cov.get("events", True),
        })
    return sorted((s for s in out if s["year"]), key=lambda s: s["year"], reverse=True)


def pick_seasons(seasons, n_completed=DEFAULT_SEASONS, include_current=False):
    current = next((s for s in seasons if s["current"]), None)
    current_year = current["year"] if current else None
    completed = [s for s in seasons if current_year is None or s["year"] < current_year]
    chosen = completed[:n_completed]
    if include_current and current:
        chosen = [current] + chosen
    return chosen


def finished_fixtures(league_id, season):
    payload = af.api_get("/fixtures", {"league": league_id, "season": season, "status": "FT"})
    return payload.get("response") or []


def fixtures_with_events(fixture_ids):
    """{fixture_id: events} for up to 20 ids in one call; per-fixture fallback."""
    payload = af.api_get("/fixtures", {"ids": "-".join(str(i) for i in fixture_ids)})
    out = {}
    for item in payload.get("response") or []:
        fid = (item.get("fixture") or {}).get("id")
        if fid is not None and "events" in item:
            out[fid] = item.get("events") or []
    for fid in fixture_ids:
        if fid not in out:
            ev = af.api_get("/fixtures/events", {"fixture": fid})
            out[fid] = ev.get("response") or []
    return out


# --- goal events -> sides ----------------------------------------------------

def is_scoring_goal(event):
    """Same rule as the live results collector: missed penalties never score."""
    if (event.get("type") or "").strip() != "Goal":
        return False
    detail = (event.get("detail") or "").strip().lower()
    comments = (event.get("comments") or "").strip().lower()
    return "missed" not in detail and "missed" not in comments


def _minute(event):
    t = event.get("time") or {}
    try:
        elapsed = int(t.get("elapsed") or 0)
    except (TypeError, ValueError):
        elapsed = 0
    try:
        extra = int(t.get("extra") or 0)
    except (TypeError, ValueError):
        extra = 0
    return elapsed, extra


def resolve_goals(events, home_id, away_id, home_name, away_name, fthg, ftag):
    """
    Return (goals, own_goal_rule, reason). goals = [(elapsed, side, team, player, detail)].

    Own goals: tries "event team = team that conceded it" first, then "event
    team = team credited"; keeps whichever reproduces the official score.
    """
    goals = [e for e in events if is_scoring_goal(e)]
    goals.sort(key=_minute)

    def side_of(event):
        team = event.get("team") or {}
        tid, tname = team.get("id"), normalize_team(team.get("name") or "")
        if tid is not None and tid == home_id or tname and tname == home_name:
            return 1
        if tid is not None and tid == away_id or tname and tname == away_name:
            return 2
        return None

    has_og = any("own" in (e.get("detail") or "").lower() for e in goals)
    rules = ("flip", "as_is") if has_og else ("none",)
    for rule in rules:
        rows = []
        ok = True
        for e in goals:
            side = side_of(e)
            if side is None:
                ok = False
                break
            if rule == "flip" and "own" in (e.get("detail") or "").lower():
                side = 3 - side
            elapsed, _extra = _minute(e)
            team = home_name if side == 1 else away_name
            rows.append((elapsed, side, team,
                         ((e.get("player") or {}).get("name")) or "",
                         e.get("detail") or ""))
        if not ok:
            return None, None, "goal_team_unmatched"
        if (sum(r[1] == 1 for r in rows), sum(r[1] == 2 for r in rows)) == (fthg, ftag):
            return rows, rule, None
    return None, None, f"events_do_not_match_final_{fthg}-{ftag}"


def official_score(item):
    ft = ((item.get("score") or {}).get("fulltime") or {})
    home, away = ft.get("home"), ft.get("away")
    if home is None or away is None:
        goals = item.get("goals") or {}
        home, away = goals.get("home"), goals.get("away")
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None, None


# --- main ------------------------------------------------------------------------

def process_batch(batch, league, season, seen, stats):
    events_by_id = fixtures_with_events([(i.get("fixture") or {}).get("id") for i in batch])
    for item in batch:
        fixture = item.get("fixture") or {}
        fid = fixture.get("id")
        oid = f"af-{fid}"
        teams = item.get("teams") or {}
        home_t, away_t = teams.get("home") or {}, teams.get("away") or {}
        home = normalize_team(home_t.get("name") or "")
        away = normalize_team(away_t.get("name") or "")
        fthg, ftag = official_score(item)
        if fthg is None:
            reason = "no_final_score"
            rows = None
        else:
            rows, rule, reason = resolve_goals(
                events_by_id.get(fid, []), home_t.get("id"), away_t.get("id"),
                home, away, fthg, ftag,
            )
        if reason:
            stats["incomplete"] += 1
            append_rows(SKIPPED, SKIPPED_FIELDS, [{
                "id_odsp": oid, "league": league, "season": season, "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
            }])
            continue
        stats["og_rule"][rule] = stats["og_rule"].get(rule, 0) + 1
        # Events before the match row: a crash in between re-fetches the match,
        # and the importer drops duplicate goal rows.
        append_rows(EVENTS, EVENT_FIELDS, [{
            "id_odsp": oid, "time": minute, "event_type": 1, "event_type2": detail,
            "side": side, "event_team": team, "player": player, "is_goal": 1,
            "situation": "",
        } for minute, side, team, player, detail in rows])
        append_rows(GINF, GINF_FIELDS, [{
            "id_odsp": oid, "date": (fixture.get("date") or "")[:10],
            "league": league, "season": str(season),
            "country": ((item.get("league") or {}).get("country")) or "",
            "ht": home, "at": away, "fthg": fthg, "ftag": ftag,
            "odd_h": "", "odd_d": "", "odd_a": "",
        }])
        seen.add(oid)
        stats["added"] += 1
        stats["goals"] += len(rows)


def probe(league_id):
    def show(label, obj):
        print(f"\n=== {label} ===\n{json.dumps(obj, indent=2, default=str)[:2500]}")

    seasons = league_seasons(league_id)
    show(f"seasons for league {league_id} (newest first)", seasons[:7])
    chosen = pick_seasons(seasons)
    print(f"\nwould collect seasons: {[s['year'] for s in chosen]}")
    completed = [s for s in chosen if not s["current"]]
    if not completed:
        return 1
    fixtures = finished_fixtures(league_id, completed[0]["year"])
    print(f"finished fixtures in {completed[0]['year']}: {len(fixtures)}")
    if not fixtures:
        return 1
    sample = fixtures[:BATCH]
    events = fixtures_with_events([(i.get("fixture") or {}).get("id") for i in sample])
    item = sample[0]
    show("first fixture (trimmed)", {k: item.get(k) for k in ("fixture", "teams", "goals", "score")})
    show("its events", events.get(item["fixture"]["id"], []))
    ok = bad = 0
    for it in sample:
        t = it.get("teams") or {}
        fthg, ftag = official_score(it)
        _rows, _rule, reason = resolve_goals(
            events.get(it["fixture"]["id"], []),
            (t.get("home") or {}).get("id"), (t.get("away") or {}).get("id"),
            normalize_team((t.get("home") or {}).get("name") or ""),
            normalize_team((t.get("away") or {}).get("name") or ""),
            fthg, ftag,
        )
        if reason:
            bad += 1
            print(f"  {it['fixture']['id']}: {reason}")
        else:
            ok += 1
    print(f"\ncheck: {ok}/{ok + bad} sample fixtures parse cleanly"
          f"{' — OK' if bad == 0 else ''}; calls left today: {af.remaining_today()}")
    return 0 if bad == 0 else 1


def done_key(league_id, season):
    return f"{league_id}:{season}"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, action="append",
                        help="Repeatable; default all SUPPORTED_LEAGUE_IDS")
    parser.add_argument("--season", type=int, action="append",
                        help="Explicit season year(s); overrides --seasons")
    parser.add_argument("--seasons", type=int, default=DEFAULT_SEASONS,
                        help="Completed seasons per league (default 5)")
    parser.add_argument("--include-current", action="store_true",
                        help="Also collect the in-progress season (live collector covers it)")
    parser.add_argument("--refresh-seasons", action="store_true",
                        help="Ignore the 7-day season-list cache")
    parser.add_argument("--retry-skipped", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv)

    af.require_key()
    league_ids = args.league_id or list(SUPPORTED_LEAGUE_IDS)
    unknown = [i for i in league_ids if i not in SUPPORTED_LEAGUE_IDS]
    if unknown:
        raise SystemExit(f"Not in SUPPORTED_LEAGUE_IDS: {unknown}")

    if args.probe:
        return probe(league_ids[0])

    seen = existing_ids(GINF)
    done = set()
    if DONE.exists():
        with DONE.open(newline="", encoding="utf-8") as handle:
            done = {row["key"] for row in csv.DictReader(handle)}
    skipped_before = set() if args.retry_skipped else existing_ids(SKIPPED)
    print(f"Leagues: {len(league_ids)}  already stored: {len(seen)}  "
          f"previously skipped: {len(skipped_before)}  reserve: {af.RESERVE}")
    stats = {"added": 0, "goals": 0, "incomplete": 0, "og_rule": {}}
    stopped = None
    try:
        for league_id in league_ids:
            league = SUPPORTED_LEAGUE_IDS[league_id]
            if args.season:
                years = list(args.season)
                current_years = set()
            else:
                chosen = pick_seasons(
                    league_seasons(league_id, args.refresh_seasons),
                    args.seasons, args.include_current,
                )
                for s in chosen:
                    if s["events_covered"] is False:
                        print(f"  {league} {s['year']}: no event coverage on api-sports — skipped")
                years = [s["year"] for s in chosen if s["events_covered"] is not False]
                current_years = {s["year"] for s in chosen if s["current"]}
            for season in years:
                key = done_key(league_id, season)
                if key in done and not args.season and not args.retry_skipped:
                    continue
                fixtures = finished_fixtures(league_id, season)
                todo = [
                    i for i in fixtures
                    if f"af-{(i.get('fixture') or {}).get('id')}" not in seen
                    and f"af-{(i.get('fixture') or {}).get('id')}" not in skipped_before
                ]
                print(f"  {league} {season}: {len(fixtures)} finished, {len(todo)} new "
                      f"(calls left today: {af.remaining_today()})")
                for start in range(0, len(todo), BATCH):
                    process_batch(todo[start:start + BATCH], league, season, seen, stats)
                if season not in current_years and not args.season:
                    append_rows(DONE, DONE_FIELDS, [{
                        "key": key, "league": league, "season": season,
                        "matches": len(fixtures),
                        "at": datetime.now(timezone.utc).isoformat(),
                    }])
                    done.add(key)
    except af.QuotaExhausted as exc:
        stopped = f"daily quota ({exc})"
    except af.AuthError as exc:
        print(f"api-sports refused the request: {exc}")
        print("Check the key and that your plan covers these seasons.")
        return 2

    print(f"added {stats['added']} matches ({stats['goals']} goals), "
          f"skipped as incomplete {stats['incomplete']}, "
          f"own-goal rule used {stats['og_rule']}, calls this run {af.calls_made()}")
    if stopped:
        print(f"Stopped early: {stopped}. Rerun (or let cron) continue tomorrow.")
        return EXIT_PARTIAL
    return 0


if __name__ == "__main__":
    sys.exit(main())
