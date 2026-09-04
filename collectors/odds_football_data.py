"""
Pull opening + closing 1X2 back prices from football-data.co.uk CSVs.

No API key. Files update about twice a week.
Opening columns (since 2019/20): B365H / B365A
Closing columns: B365CH / B365CA
Pinnacle fallback: PSH / PSA and PSCH / PSCA.

Lay is left empty. opportunities_engine estimates it.
"""

import csv
import io
import sys
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db, save_odds_history
from team_normalizer import normalize_team

# mmz4281/{yy}{yy+1}/{code}.csv  e.g. 2627 = 2026/27
SEASON_CODES = ["2627", "2526"]

MAIN_DIVISIONS = {
    "E0": "Premier League",
    "E1": "Championship",
    "E2": "League One",
    "E3": "League Two",
    "SC0": "Premiership",
    "D1": "Bundesliga",
    "D2": "2. Bundesliga",
    "SP1": "La Liga",
    "I1": "Serie A",
    "F1": "Ligue 1",
    "N1": "Eredivisie",
    "B1": "Jupiler Pro League",
    "P1": "Primeira Liga",
}

# Extra-leagues pack (single rolling file per country).
EXTRA_FILES = {
    "https://www.football-data.co.uk/new/USA.csv": "Major League Soccer",
    "https://www.football-data.co.uk/new/DNK.csv": "Superliga",
    "https://www.football-data.co.uk/new/NOR.csv": "Eliteserien",
    "https://www.football-data.co.uk/new/SWE.csv": "Allsvenskan",
    "https://www.football-data.co.uk/new/IRL.csv": "Premier Division",
}

BOOKS = [
    ("bet365", "B365H", "B365A", "B365CH", "B365CA"),
    ("pinnacle", "PSH", "PSA", "PSCH", "PSCA"),
]


def season_url(season_code, div_code):
    return f"https://www.football-data.co.uk/mmz4281/{season_code}/{div_code}.csv"


def parse_date(raw):
    raw = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def to_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def already_saved(match_id, bookmaker, selection, back_odds):
    conn = get_db()
    row = conn.execute(
        """
        SELECT 1 FROM odds_history
        WHERE match_id = ?
          AND bookmaker = ?
          AND selection = ?
          AND back_odds = ?
        LIMIT 1
        """,
        (match_id, bookmaker, selection, back_odds),
    ).fetchone()
    conn.close()
    return row is not None


def save_price(match_id, kickoff, league, home, away, selection, bookmaker, price):
    if price is None:
        return False
    if already_saved(match_id, bookmaker, selection, price):
        return False
    save_odds_history(
        match_id=match_id,
        kickoff=kickoff,
        league=league,
        home_team=home,
        away_team=away,
        selection=selection,
        bookmaker=bookmaker,
        back_odds=price,
        lay_odds=None,
    )
    return True


def ingest_rows(rows, league_name):
    saved = 0
    skipped = 0

    for row in rows:
        home_raw = row.get("HomeTeam") or row.get("Home") or ""
        away_raw = row.get("AwayTeam") or row.get("Away") or ""
        if not home_raw or not away_raw:
            skipped += 1
            continue

        home = normalize_team(home_raw)
        away = normalize_team(away_raw)
        kickoff = parse_date(row.get("Date") or row.get("date") or "")
        match_id = f"fd-{league_name}-{kickoff}-{home}-{away}"

        for bookmaker, open_h, open_a, close_h, close_a in BOOKS:
            opening_home = to_float(row.get(open_h))
            opening_away = to_float(row.get(open_a))
            closing_home = to_float(row.get(close_h))
            closing_away = to_float(row.get(close_a))

            # Opening first so get_odds_movement treats it as the open.
            if save_price(match_id, kickoff, league_name, home, away, home, bookmaker, opening_home):
                saved += 1
            if save_price(match_id, kickoff, league_name, home, away, away, bookmaker, opening_away):
                saved += 1
            if closing_home and closing_home != opening_home:
                if save_price(match_id, kickoff, league_name, home, away, home, bookmaker, closing_home):
                    saved += 1
            if closing_away and closing_away != opening_away:
                if save_price(match_id, kickoff, league_name, home, away, away, bookmaker, closing_away):
                    saved += 1

            if opening_home is None and opening_away is None and closing_home is None:
                skipped += 1

    return saved, skipped


def download_csv(url):
    response = requests.get(url, timeout=45)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def collect_football_data_odds():
    total_saved = 0
    total_skipped = 0

    for season in SEASON_CODES:
        season_hit = False
        for div_code, league_name in MAIN_DIVISIONS.items():
            url = season_url(season, div_code)
            try:
                rows = download_csv(url)
            except Exception as exc:
                print(f"{url} failed: {exc}")
                continue
            if not rows:
                print(f"{league_name} {season}: no file")
                continue
            season_hit = True
            saved, skipped = ingest_rows(rows, league_name)
            print(f"{league_name} {season}: {len(rows)} matches, +{saved} odds rows")
            total_saved += saved
            total_skipped += skipped
        if season_hit:
            break

    for url, league_name in EXTRA_FILES.items():
        try:
            rows = download_csv(url)
        except Exception as exc:
            print(f"{league_name} extra failed: {exc}")
            continue
        if not rows:
            print(f"{league_name}: extra file missing")
            continue
        saved, skipped = ingest_rows(rows, league_name)
        print(f"{league_name} extra: {len(rows)} matches, +{saved} odds rows")
        total_saved += saved
        total_skipped += skipped

    print(f"Saved {total_saved} odds rows from football-data.co.uk")
    print(f"Skipped {total_skipped} empty/duplicate rows")


if __name__ == "__main__":
    collect_football_data_odds()
