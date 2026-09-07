#!/usr/bin/env python3
"""
Backfill via TheStatsAPI into data/ginf_api.csv and data/events_api.csv.
Does not touch Understat data/ginf.csv or data/events.csv.

Default: the 13 supported leagues Understat does not cover.
Pass --include-understat to also hit PL/La Liga/etc (wastes quota).

    python3 -u collectors/backfill_thestatsapi.py --league Championship --year 2024
    python3 -u collectors/backfill_thestatsapi.py
"""
import argparse
import csv
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from collectors.thestatsapi import (
    api_get,
    find_competition_id,
    flatten := None,
)
from collectors import thestatsapi as ts
from constants import SUPPORTED_LEAGUES
from team_normalizer import normalize_team

UNDERSTAT_LEAGUES = {
    "Premier League",
    "La Liga",
    "Bundesliga",
    "Serie A",
    "Ligue 1",
    "Russian Premier League",
}
YEARS = [2020, 2021, 2022, 2023, 2024]
GINF_API = PROJECT_ROOT / "data" / "ginf_api.csv"
EVENTS_API = PROJECT_ROOT / "data" / "events_api.csv"
GINF_FIELDS = ["id_odsp", "date", "league", "season", "country", "ht", "at", "fthg", "ftag", "odd_h", "odd_d", "odd_a"]
EVENT_FIELDS = ["id_odsp", "time", "event_type", "event_type2", "side", "event_team", "player", "is_goal", "situation"]


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


def season_id_for_year(competition_id, year):
    payload = ts.api_get(f"/football/competitions/{competition_id}/seasons")
    rows = ts.unwrap(payload) or []
    if isinstance(rows, dict):
        rows = [rows]
    year_s = str(year)
    for row in rows:
        name = str(row.get("name") or row.get("season") or row.get("id") or "")
        start = str(row.get("start_year") or row.get("year") or "")
        if year_s in name or start == year_s:
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
    return []


def side_name(match, key):
    block = match.get(key) or match.get(f"{key}_team") or {}
    if isinstance(block, dict):
        return block.get("name") or ""
    return ""


def side_score(match, key):
    block = match.get(key) or {}
    if isinstance(block, dict) and block.get("score") is not None:
        return block.get("score")
    score = match.get("score") or {}
    if isinstance(score, dict):
        return score.get(key)
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", action="append")
    parser.add_argument("--year", type=int, action="append")
    parser.add_argument("--include-understat", action="store_true")
    args = parser.parse_args()
    years = args.year or YEARS
    if args.league:
        leagues = args.league
    elif args.include_understat:
        leagues = list(SUPPORTED_LEAGUES)
    else:
        leagues = [name for name in SUPPORTED_LEAGUES if name not in UNDERSTAT_LEAGUES]
    seen = existing_ids(GINF_API)
    print(f"Leagues: {leagues}")
    print(f"Years: {years}")
    print(f"Already in ginf_api.csv: {len(seen)}")
    added = goals_n = skipped = failed = 0
    for league in leagues:
        try:
            cid = ts.find_competition_id(league)
        except Exception as exc:
            print(f"{league}: lookup failed ({exc})")
            continue
        if not cid:
            continue
        for year in years:
            sid = season_id_for_year(cid, year)
            if not sid:
                print(f"  {league} {year}: no season id")
                continue
            try:
                matches = list_finished(cid, sid)
            except Exception as exc:
                print(f"  {league} {year}: list failed ({exc})")
                continue
            print(f"  {league} {year}: {len(matches)} finished")
            for match in matches:
                mid = ts.match_id_of(match)
                if not mid:
                    continue
                oid = f"ts-{mid}"
                if oid in seen:
                    skipped += 1
                    continue
                home = normalize_team(side_name(match, "home"))
                away = normalize_team(side_name(match, "away"))
                date = (ts.kickoff_of(match) or "")[:10]
                try:
                    events = timeline_goals(mid)
                except Exception as exc:
                    failed += 1
                    print(f"    timeline failed {mid}: {exc}")
                    continue
                event_rows = []
                for event in events:
                    if str(event.get("type") or "").lower() != "goal":
                        continue
                    team = normalize_team(((event.get("team") or {}).get("name")) or "")
                    side = 1 if team == home else 2 if team == away else ""
                    if side == "":
                        continue
                    minute = int(event.get("minute") or 0) + int(event.get("extra_time") or 0)
                    player = ((event.get("player") or {}).get("name")) or ""
                    event_rows.append({
                        "id_odsp": oid, "time": minute, "event_type": 1,
                        "event_type2": "", "side": side, "event_team": team,
                        "player": player, "is_goal": 1, "situation": event.get("period") or "",
                    })
                    goals_n += 1
                append_rows(GINF_API, GINF_FIELDS, [{
                    "id_odsp": oid, "date": date, "league": league,
                    "season": str(year), "country": "", "ht": home, "at": away,
                    "fthg": side_score(match, "home"), "ftag": side_score(match, "away"),
                    "odd_h": "", "odd_d": "", "odd_a": "",
                }])
                if event_rows:
                    append_rows(EVENTS_API, EVENT_FIELDS, event_rows)
                seen.add(oid)
                added += 1
    print(f"added {added} matches, {goals_n} goals, skipped {skipped}, failed {failed}")
    print("Understat ginf.csv / events.csv not modified")


if __name__ == "__main__":
    main()
