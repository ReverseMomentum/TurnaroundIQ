#!/usr/bin/env python3
"""
Understat leagues only (not Championship / MLS / Nordic etc):
  EPL, La_liga, Bundesliga, Serie_A, Ligue_1, RFPL

    python3 -u scrape_understat_multi.py
    python3 -u scrape_understat_multi.py --league EPL --league La_liga
    python3 -u scrape_understat_multi.py --year 2024
"""
import argparse
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

LEAGUES = {
    "EPL": "Premier League",
    "La_liga": "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie_A": "Serie A",
    "Ligue_1": "Ligue 1",
    "RFPL": "Russian Premier League",
}

SLEEP = 1.2
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept-Language": "en-GB,en;q=0.9",
}
TEAM_MAP = {
    "Manchester City": "Man City", "Manchester United": "Man Utd",
    "Newcastle United": "Newcastle", "Wolverhampton Wanderers": "Wolves",
    "West Bromwich Albion": "West Brom", "Sheffield United": "Sheffield Utd",
    "Brighton and Hove Albion": "Brighton", "Nottingham Forest": "Nott'm Forest",
    "Leeds United": "Leeds",
}
STATS_COLS = ["fixture_id","season","matchweek","date","home_team","away_team","home_goals","away_goals","xg_home","xg_away","source"]
EVENTS_COLS = ["event_id","fixture_id","season","date","home_team","away_team","minute","event_team","event_type","scorer","assist","is_penalty","is_own_goal","score_after","source"]
ROOT = Path(__file__).resolve().parent
STATS_DIR = ROOT / "stats"
DATA_DIR = ROOT / "data"
STATS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

def canon(name):
    return TEAM_MAP.get(name or "", name or "")

def flatten_shots(shots):
    if isinstance(shots, list):
        return shots
    if isinstance(shots, dict):
        return list(shots.get("h") or []) + list(shots.get("a") or [])
    return []

def season_label(year):
    return f"{year}/{str(year+1)[-2:]}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", action="append", choices=sorted(LEAGUES), help="Repeatable. Default: all Understat leagues")
    parser.add_argument("--year", type=int, action="append", help="Start year, e.g. 2024. Default: 2020-2025")
    args = parser.parse_args()
    leagues = args.league or list(LEAGUES)
    years = args.year or YEARS

    stats_rows, event_rows, ginf_rows, pipe_events = [], [], [], []
    fid_i = eid = 1

    for slug in leagues:
        pipeline_name = LEAGUES[slug]
        for year in years:
            print(f"\n=== {pipeline_name} {season_label(year)} ===")
            payload = requests.get(
                f"https://understat.com/getLeagueData/{slug}/{year}",
                headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{slug}/{year}"},
                timeout=30,
            )
            if payload.status_code != 200:
                print(f"  skip {slug} {year}: HTTP {payload.status_code}")
                continue
            try:
                matches = payload.json().get("dates") or []
            except Exception as exc:
                print(f"  skip {slug} {year}: {exc}")
                continue
            print(f"  {len(matches)} matches")
            for match in matches:
                mid = match.get("id")
                home = canon((match.get("h") or {}).get("title"))
                away = canon((match.get("a") or {}).get("title"))
                goals = match.get("goals") or {}
                xg = match.get("xG") or {}
                try:
                    hg, ag = int(goals.get("h") or 0), int(goals.get("a") or 0)
                except (TypeError, ValueError):
                    continue
                try:
                    xgh, xga = round(float(xg.get("h") or 0), 2), round(float(xg.get("a") or 0), 2)
                except (TypeError, ValueError):
                    xgh = xga = ""
                raw_dt = match.get("datetime") or ""
                iso_date = uk_date = ""
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        parsed = datetime.strptime(str(raw_dt)[:19], fmt)
                        iso_date, uk_date = parsed.strftime("%Y-%m-%d"), parsed.strftime("%d/%m/%Y")
                        break
                    except ValueError:
                        continue
                fid = f"{slug.lower()}-{year}-{fid_i:05d}"
                fid_i += 1
                stats_rows.append({"fixture_id": fid, "season": season_label(year), "matchweek": match.get("round") or "", "date": uk_date, "home_team": home, "away_team": away, "home_goals": hg, "away_goals": ag, "xg_home": xgh, "xg_away": xga, "source": "understat"})
                ginf_rows.append({"id_odsp": fid, "date": iso_date, "league": pipeline_name, "season": str(year), "country": "", "ht": home, "at": away, "fthg": hg, "ftag": ag, "odd_h": "", "odd_d": "", "odd_a": ""})
                shots = []
                if mid:
                    try:
                        shot_resp = requests.get(
                            f"https://understat.com/getMatchData/{mid}",
                            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/match/{mid}"},
                            timeout=30,
                        )
                        shot_resp.raise_for_status()
                        shots = flatten_shots(shot_resp.json().get("shots"))
                    except Exception as exc:
                        print(f"    shots failed {home} vs {away}: {exc}")
                sh = sa = 0
                for shot in shots:
                    if shot.get("result") != "Goal":
                        continue
                    ha = shot.get("h_a")
                    team = home if ha == "h" else away
                    side = 1 if ha == "h" else 2
                    if ha == "h": sh += 1
                    else: sa += 1
                    stype = shot.get("situation") or shot.get("shotType") or ""
                    is_pen = int(str(stype).lower() in {"penalty", "pen"})
                    is_og = int("own" in str(stype).lower())
                    try: minute = int(float(shot.get("minute") or 0))
                    except (TypeError, ValueError): minute = 0
                    scorer = shot.get("player") or ""
                    event_rows.append({"event_id": f"ev-{eid:06d}", "fixture_id": fid, "season": season_label(year), "date": uk_date, "home_team": home, "away_team": away, "minute": minute, "event_team": team, "event_type": "penalty" if is_pen else "own_goal" if is_og else "goal", "scorer": scorer, "assist": shot.get("player_assisted") or "", "is_penalty": is_pen, "is_own_goal": is_og, "score_after": f"{sh}-{sa}", "source": "understat"})
                    pipe_events.append({"id_odsp": fid, "time": minute, "event_type": 1, "event_type2": "", "side": side, "event_team": team, "player": scorer, "is_goal": 1, "situation": stype})
                    eid += 1
                time.sleep(SLEEP)
            print(f"  cumulative: {len(stats_rows)} fixtures, {len(event_rows)} goals")

    pd.DataFrame(stats_rows, columns=STATS_COLS).to_csv(STATS_DIR / "all_20_25.csv", index=False)
    pd.DataFrame(event_rows, columns=EVENTS_COLS).to_csv(STATS_DIR / "all_events.csv", index=False)
    pd.DataFrame(ginf_rows).to_csv(DATA_DIR / "ginf.csv", index=False)
    pd.DataFrame(pipe_events).to_csv(DATA_DIR / "events.csv", index=False)
    print(f"\nDone. {len(stats_rows)} fixtures, {len(event_rows)} goals")
    print("Wrote stats/all_20_25.csv, stats/all_events.csv, data/ginf.csv, data/events.csv")

if __name__ == "__main__":
    main()
