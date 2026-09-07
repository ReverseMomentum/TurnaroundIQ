#!/usr/bin/env python3
"""
Backfill past seasons via API-Football into SEPARATE files:
  data/ginf_api.csv
  data/events_api.csv

Does not touch data/ginf.csv or data/events.csv (Understat Big 5).

    python3 -u collectors/backfill_api_football.py --league-id 40 --season 2024
    python3 -u collectors/backfill_api_football.py --league-id 40 --season 2023
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from constants import API_FOOTBALL_KEY, SUPPORTED_LEAGUE_IDS
from team_normalizer import normalize_team

HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}
SLEEP = 3.0
GINF_API = PROJECT_ROOT / "data" / "ginf_api.csv"
EVENTS_API = PROJECT_ROOT / "data" / "events_api.csv"
GINF_FIELDS = ["id_odsp", "date", "league", "season", "country", "ht", "at", "fthg", "ftag", "odd_h", "odd_d", "odd_a"]
EVENT_FIELDS = ["id_odsp", "time", "event_type", "event_type2", "side", "event_team", "player", "is_goal", "situation"]


def existing_ids(path):
    if not path.exists():
        return set()
    ids = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ids.add(row.get("id_odsp", ""))
    return ids


def append_rows(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def list_fixtures(league_id, season):
    url = "https://v3.football.api-sports.io/fixtures"
    resp = requests.get(
        url,
        headers=HEADERS,
        params={"league": league_id, "season": season, "status": "FT"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API errors: {errors}")
    return payload.get("response") or []


def list_events(fixture_id):
    url = "https://v3.football.api-sports.io/fixtures/events"
    resp = requests.get(
        url,
        headers=HEADERS,
        params={"fixture": fixture_id},
        timeout=30,
    )
    if resp.status_code == 429:
        raise RuntimeError("rate limited")
    resp.raise_for_status()
    return resp.json().get("response") or []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, required=True)
    parser.add_argument("--season", type=int, required=True, help="Start year, e.g. 2024")
    args = parser.parse_args()
    if args.league_id not in SUPPORTED_LEAGUE_IDS:
        raise SystemExit(f"{args.league_id} is not in SUPPORTED_LEAGUE_IDS")
    league = SUPPORTED_LEAGUE_IDS[args.league_id]
    seen = existing_ids(GINF_API)
    print(f"Backfill {league} {args.season} -> {GINF_API.name} ({len(seen)} matches already stored)")
    fixtures = list_fixtures(args.league_id, args.season)
    print(f"{len(fixtures)} FT fixtures from API")
    added = goals = skipped = failed = 0
    for item in fixtures:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        goals_block = item.get("goals") or {}
        league_meta = item.get("league") or {}
        fid = str(fixture.get("id") or "")
        if not fid:
            continue
        oid = f"api-{fid}"
        if oid in seen:
            skipped += 1
            continue
        home = normalize_team((teams.get("home") or {}).get("name") or "")
        away = normalize_team((teams.get("away") or {}).get("name") or "")
        date = (fixture.get("date") or "")[:10]
        try:
            events = list_events(fid)
        except Exception as exc:
            failed += 1
            print(f"  events failed {fid}: {exc}")
            time.sleep(SLEEP * 3)
            continue
        event_rows = []
        for event in events:
            if event.get("type") != "Goal":
                continue
            team = normalize_team(((event.get("team") or {}).get("name")) or "")
            side = 1 if team == home else 2 if team == away else ""
            if side == "":
                continue
            minute = ((event.get("time") or {}).get("elapsed")) or 0
            extra = ((event.get("time") or {}).get("extra")) or 0
            try:
                minute = int(minute) + int(extra or 0)
            except (TypeError, ValueError):
                minute = 0
            player = ((event.get("player") or {}).get("name")) or ""
            event_rows.append({
                "id_odsp": oid,
                "time": minute,
                "event_type": 1,
                "event_type2": event.get("detail") or "",
                "side": side,
                "event_team": team,
                "player": player,
                "is_goal": 1,
                "situation": event.get("comments") or "",
            })
            goals += 1
        append_rows(GINF_API, GINF_FIELDS, [{
            "id_odsp": oid,
            "date": date,
            "league": league,
            "season": str(args.season),
            "country": league_meta.get("country") or "",
            "ht": home,
            "at": away,
            "fthg": goals_block.get("home") if goals_block.get("home") is not None else "",
            "ftag": goals_block.get("away") if goals_block.get("away") is not None else "",
            "odd_h": "",
            "odd_d": "",
            "odd_a": "",
        }])
        if event_rows:
            append_rows(EVENTS_API, EVENT_FIELDS, event_rows)
        seen.add(oid)
        added += 1
        time.sleep(SLEEP)
    print(f"added {added} matches, {goals} goals, skipped {skipped}, failed {failed}")
    print(f"Understat files untouched: data/ginf.csv data/events.csv")


if __name__ == "__main__":
    main()
