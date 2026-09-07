#!/usr/bin/env python3
"""scrape_epl_multi.py - EPL 2020/21-2025/26 via getLeagueData."""
import json, re, time
from datetime import datetime
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup

SEASONS = {2020: "2020/21", 2021: "2021/22", 2022: "2022/23", 2023: "2023/24", 2024: "2024/25", 2025: "2025/26"}
LEAGUE_URL = "https://understat.com/league/EPL/{year}"
LEAGUE_DATA_URL = "https://understat.com/getLeagueData/EPL/{year}"
MATCH_URL = "https://understat.com/match/{mid}"
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
STATS_COLS = ["fixture_id","season","matchweek","date","home_team","away_team","home_goals","away_goals","xg_home","xg_away","possession_home","possession_away","shots_home","shots_away","shots_on_target_home","shots_on_target_away","corners_home","corners_away","fouls_home","fouls_away","yellow_cards_home","yellow_cards_away","red_cards_home","red_cards_away","source"]
EVENTS_COLS = ["event_id","fixture_id","season","date","home_team","away_team","minute","event_team","event_type","scorer","assist","is_penalty","is_own_goal","score_after","source"]
ROOT = Path(__file__).resolve().parent
STATS_DIR = ROOT / "stats"
DATA_DIR = ROOT / "data"
STATS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

def fetch(url, retries=4):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(8 * (i + 1)); continue
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last = exc
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Failed {url}: {last}")

def json_from_script(html, key):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script"):
        text = tag.get_text() or ""
        if key not in text:
            continue
        found = re.search(r"JSON\.parse\('(.+?)'\)", text, re.DOTALL)
        if not found:
            continue
        raw = found.group(1).encode("utf-8").decode("unicode_escape")
        return json.loads(raw)
    raise ValueError(f"Could not find {key}")

def canon(name):
    return TEAM_MAP.get(name or "", name or "")

def flatten_shots(shots):
    if isinstance(shots, list):
        return shots
    if isinstance(shots, dict):
        return list(shots.get("h") or []) + list(shots.get("a") or [])
    return []

def main():
    stats_rows, event_rows, ginf_rows, pipe_events = [], [], [], []
    fid_i = eid = 1
    for year, label in SEASONS.items():
        print(f"\n=== {label} ===")
        payload = requests.get(
            LEAGUE_DATA_URL.format(year=year),
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": LEAGUE_URL.format(year=year)},
            timeout=30,
        )
        payload.raise_for_status()
        matches = payload.json().get("dates") or []
        print(f"  {len(matches)} matches from getLeagueData")
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
            fid = f"pl-{year}-{fid_i:04d}"
            fid_i += 1
            stats_rows.append({"fixture_id": fid, "season": label, "matchweek": match.get("round") or "", "date": uk_date, "home_team": home, "away_team": away, "home_goals": hg, "away_goals": ag, "xg_home": xgh, "xg_away": xga, "possession_home": "", "possession_away": "", "shots_home": "", "shots_away": "", "shots_on_target_home": "", "shots_on_target_away": "", "corners_home": "", "corners_away": "", "fouls_home": "", "fouls_away": "", "yellow_cards_home": "", "yellow_cards_away": "", "red_cards_home": "", "red_cards_away": "", "source": "understat"})
            ginf_rows.append({"id_odsp": fid, "date": iso_date, "league": "Premier League", "season": str(year), "country": "england", "ht": home, "at": away, "fthg": hg, "ftag": ag, "odd_h": "", "odd_d": "", "odd_a": ""})
            shots = []
            if mid:
                try:
                    shots = flatten_shots(json_from_script(fetch(MATCH_URL.format(mid=mid)), "shotsData"))
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
                event_rows.append({"event_id": f"ev-{eid:05d}", "fixture_id": fid, "season": label, "date": uk_date, "home_team": home, "away_team": away, "minute": minute, "event_team": team, "event_type": "penalty" if is_pen else "own_goal" if is_og else "goal", "scorer": scorer, "assist": shot.get("player_assisted") or "", "is_penalty": is_pen, "is_own_goal": is_og, "score_after": f"{sh}-{sa}", "source": "understat"})
                pipe_events.append({"id_odsp": fid, "time": minute, "event_type": 1, "event_type2": "", "side": side, "event_team": team, "player": scorer, "is_goal": 1, "situation": stype})
                eid += 1
            time.sleep(SLEEP)
        print(f"  cumulative: {len(stats_rows)} fixtures, {len(event_rows)} goals")
    pd.DataFrame(stats_rows, columns=STATS_COLS).to_csv(STATS_DIR / "prem_20_25.csv", index=False)
    pd.DataFrame(event_rows, columns=EVENTS_COLS).to_csv(STATS_DIR / "prem_events.csv", index=False)
    pd.DataFrame(ginf_rows).to_csv(DATA_DIR / "ginf.csv", index=False)
    pd.DataFrame(pipe_events).to_csv(DATA_DIR / "events.csv", index=False)
    print(f"\nDone. {len(stats_rows)} fixtures, {len(event_rows)} goals")

if __name__ == "__main__":
    main()
