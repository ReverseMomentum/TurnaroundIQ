"""
Write data/ginf.csv and data/events.csv from FBref.
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from progress import ProgressBar, ok, step, warn
from team_normalizer import normalize_team

DATA_DIR = PROJECT_ROOT / "data"
GINF_FILE = DATA_DIR / "ginf.csv"
EVENT_FILE = DATA_DIR / "events.csv"

FIRST_SEASON = 2017
SLEEP_SECONDS = 18.0
SEASON_SLEEP_SECONDS = 45.0
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TurnaroundIQ/1.0; "
        "historical research; +https://github.com/ReverseMomentum/TurnaroundIQ)"
    )
}

FBREF_LEAGUES = {
    "ENG-Premier League": ("Premier League", "england"),
    "ENG-Championship": ("Championship", "england"),
    "ESP-La Liga": ("La Liga", "spain"),
    "GER-Bundesliga": ("Bundesliga", "germany"),
    "ITA-Serie A": ("Serie A", "italy"),
    "FRA-Ligue 1": ("Ligue 1", "france"),
    "NED-Eredivisie": ("Eredivisie", "netherlands"),
    "POR-Primeira Liga": ("Primeira Liga", "portugal"),
    "BEL-Jupiler Pro League": ("Jupiler Pro League", "belgium"),
    "USA-Major League Soccer": ("Major League Soccer", "usa"),
}

GINF_FIELDS = [
    "id_odsp", "date", "league", "season", "country",
    "ht", "at", "fthg", "ftag", "odd_h", "odd_d", "odd_a",
]
EVENT_FIELDS = [
    "id_odsp", "time", "event_type", "event_type2", "side",
    "event_team", "player", "is_goal", "situation",
]


def season_list(start=FIRST_SEASON):
    import datetime
    return list(range(start, datetime.datetime.utcnow().year + 1))


def _cell(row, *names):
    for name in names:
        if name in getattr(row, "index", []):
            value = row[name]
            if value == value:
                return value
        for key in getattr(row, "index", []):
            if str(key).lower() == name.lower():
                value = row[key]
                if value == value:
                    return value
    return None


def _score(row):
    raw = _cell(row, "score", "Score")
    if raw is None:
        return None, None
    text = str(raw).replace(" ", "")
    if "\u2013" in text:
        left, right = text.split("\u2013", 1)
        try:
            return int(left), int(right)
        except ValueError:
            return None, None
    return None, None


def _minute(raw):
    if raw is None:
        return None
    match = re.match(r"(\d+)", str(raw).strip())
    if not match:
        return None
    minute = int(match.group(1))
    extra = re.search(r"\+(\d+)", str(raw))
    if extra:
        minute += int(extra.group(1))
    return minute


def extract_url(row):
    for name in ("url", "match_url", "game_url", "href"):
        value = _cell(row, name)
        if value and str(value).startswith("http"):
            return str(value)
    for key in getattr(row, "index", []):
        text = str(row[key])
        if "fbref.com/en/matches/" in text:
            return text if text.startswith("http") else "https://fbref.com" + text
    return None


def load_existing():
    matches = {}
    events = []
    if GINF_FILE.exists():
        with GINF_FILE.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                matches[row["id_odsp"]] = row
    if EVENT_FILE.exists():
        with EVENT_FILE.open(newline="", encoding="utf-8") as handle:
            events = list(csv.DictReader(handle))
    return matches, events


def write_files(matches, events):
    DATA_DIR.mkdir(exist_ok=True)
    with GINF_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GINF_FIELDS)
        writer.writeheader()
        for row in matches.values():
            writer.writerow({key: row.get(key, "") for key in GINF_FIELDS})
    with EVENT_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for row in events:
            writer.writerow({key: row.get(key, "") for key in EVENT_FIELDS})


def goals_from_html(html, home, away):
    import pandas as pd

    goals = []
    for table in pd.read_html(html):
        joined = " ".join(str(c).lower() for c in table.columns)
        if "minute" not in joined:
            continue
        minute_col = next((c for c in table.columns if "min" in str(c).lower()), None)
        team_col = next((c for c in table.columns if str(c).lower() in {"squad", "team"}), None)
        outcome_col = next(
            (c for c in table.columns if "outcome" in str(c).lower() or "result" in str(c).lower()),
            None,
        )
        player_col = next((c for c in table.columns if "player" in str(c).lower()), None)
        if minute_col is None or team_col is None:
            continue
        for _, row in table.iterrows():
            outcome = str(row[outcome_col]).lower() if outcome_col is not None else "goal"
            if outcome and "goal" not in outcome and "own" not in outcome:
                continue
            minute = _minute(row[minute_col])
            team = normalize_team(str(row[team_col]))
            if minute is None or team not in {home, away}:
                continue
            player = str(row[player_col]) if player_col is not None else ""
            side = 1 if team == home else 2
            goals.append((minute, side, team, player))
        if goals:
            break
    goals.sort(key=lambda item: item[0])
    return goals


def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=45)
    if response.status_code == 429:
        raise RuntimeError("FBref rate limited (429)")
    response.raise_for_status()
    return response.text


def collect(leagues=None, seasons=None, sleep_s=SLEEP_SECONDS, season_sleep_s=SEASON_SLEEP_SECONDS):
    try:
        import soccerdata as sd
    except ImportError:
        warn("pip install soccerdata lxml")
        sys.exit(1)

    matches, events = load_existing()
    existing_ids = set(matches)
    wanted = leagues or list(FBREF_LEAGUES.keys())
    years = seasons or season_list()
    jobs = [(key, year) for key in wanted for year in years]
    step(f"{len(jobs)} league-seasons | {sleep_s}s/match | {season_sleep_s}s/season")
    bar = ProgressBar(len(jobs), label="FBref")

    for key, year in jobs:
        league_name, country = FBREF_LEAGUES[key]
        label = f"{league_name} {year}"
        try:
            fbref = sd.FBref(leagues=key, seasons=year, no_cache=False)
            schedule = fbref.read_schedule()
            if schedule is None or schedule.empty:
                bar.update(detail=label)
                time.sleep(season_sleep_s)
                continue
            frame = schedule.reset_index()
            inner = ProgressBar(len(frame), label=league_name[:12])
            added = 0
            for _, row in frame.iterrows():
                home = normalize_team(str(_cell(row, "home_team", "Home") or ""))
                away = normalize_team(str(_cell(row, "away_team", "Away") or ""))
                if not home or not away or home == "nan":
                    inner.update(detail="skip")
                    continue
                date = str(_cell(row, "date", "Date") or "")[:10]
                match_id = f"fbref-{league_name}-{date}-{home}-{away}"
                fthg, ftag = _score(row)
                matches[match_id] = {
                    "id_odsp": match_id,
                    "date": date,
                    "league": league_name,
                    "season": str(year),
                    "country": country,
                    "ht": home,
                    "at": away,
                    "fthg": "" if fthg is None else fthg,
                    "ftag": "" if ftag is None else ftag,
                    "odd_h": "",
                    "odd_d": "",
                    "odd_a": "",
                }
                if match_id in existing_ids:
                    inner.update(detail="cached")
                    continue
                url = extract_url(row)
                if not url:
                    inner.update(detail="no url")
                    continue
                try:
                    goals = goals_from_html(fetch_html(url), home, away)
                except Exception as exc:
                    warn(f"{home} v {away}: {exc}")
                    if "429" in str(exc):
                        write_files(matches, events)
                        raise
                    inner.update(detail="fail")
                    time.sleep(sleep_s * 2)
                    continue
                for minute, side, team, player in goals:
                    events.append({
                        "id_odsp": match_id,
                        "time": minute,
                        "event_type": 1,
                        "event_type2": "",
                        "side": side,
                        "event_team": team,
                        "player": player,
                        "is_goal": 1,
                        "situation": "",
                    })
                existing_ids.add(match_id)
                added += 1
                inner.update(detail=f"{home} {len(goals)}g")
                time.sleep(sleep_s)
            inner.finish()
            write_files(matches, events)
            ok(f"{label}: +{added} shot pages, {len(matches)} matches stored")
        except Exception as exc:
            warn(f"{label}: {exc}")
            write_files(matches, events)
            if "429" in str(exc):
                warn("Saved progress. Re-run the same command later.")
                break
        bar.update(detail=label)
        time.sleep(season_sleep_s)
    bar.finish()
    write_files(matches, events)
    ok(f"Wrote {len(matches)} matches -> {GINF_FILE}")
    ok(f"Wrote {len(events)} goal events -> {EVENT_FILE}")
    step("Next: python setup_historical_data.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league")
    parser.add_argument("--season", type=int)
    parser.add_argument("--sleep", type=float, default=SLEEP_SECONDS)
    parser.add_argument("--season-sleep", type=float, default=SEASON_SLEEP_SECONDS)
    args = parser.parse_args()
    leagues = None
    if args.league:
        hits = [k for k, v in FBREF_LEAGUES.items() if v[0].lower() == args.league.lower()]
        if not hits:
            warn(", ".join(sorted(v[0] for v in FBREF_LEAGUES.values())))
            sys.exit(1)
        leagues = hits
    seasons = [args.season] if args.season else None
    collect(
        leagues=leagues,
        seasons=seasons,
        sleep_s=args.sleep,
        season_sleep_s=args.season_sleep,
    )


if __name__ == "__main__":
    main()
