"""
Pull opening + closing 1X2 back prices from football-data.co.uk CSVs.

Backfills every season from 2015/16 so historical_matches and
odds_history both get opening prices. No API key.
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

FIRST_SEASON_START = 2015

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


def season_codes(start_year=FIRST_SEASON_START):
    now_year = datetime.utcnow().year
    codes = []
    for year in range(start_year, now_year + 1):
        codes.append(f"{year % 100:02d}{(year + 1) % 100:02d}")
    return list(reversed(codes))


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


def load_existing_odds():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT match_id, bookmaker, selection, back_odds
        FROM odds_history
        WHERE match_id LIKE 'fd-%'
        """
    ).fetchall()
    conn.close()
    return {(row[0], row[1], row[2], row[3]) for row in rows}


def attach_to_historical(home, away, kickoff, odd_h, odd_a, odd_d=None):
    if odd_h is None and odd_a is None:
        return 0
    conn = get_db()
    updated = conn.execute(
        """
        UPDATE historical_matches
        SET
            odd_h = COALESCE(odd_h, ?),
            odd_a = COALESCE(odd_a, ?),
            odd_d = COALESCE(odd_d, ?)
        WHERE home_team = ?
          AND away_team = ?
          AND (
                date = ?
                OR date LIKE ?
          )
          AND odd_h IS NULL
        """,
        (odd_h, odd_a, odd_d, home, away, kickoff, f"{kickoff}%"),
    ).rowcount
    conn.commit()
    conn.close()
    return updated or 0


def ingest_rows(rows, league_name, existing):
    saved = 0
    skipped = 0
    linked = 0

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

        bet365_open_h = to_float(row.get("B365H"))
        bet365_open_a = to_float(row.get("B365A"))
        bet365_open_d = to_float(row.get("B365D"))
        linked += attach_to_historical(
            home, away, kickoff, bet365_open_h, bet365_open_a, bet365_open_d
        )

        for bookmaker, open_h, open_a, close_h, close_a in BOOKS:
            prices = [
                (home, to_float(row.get(open_h))),
                (away, to_float(row.get(open_a))),
                (home, to_float(row.get(close_h))),
                (away, to_float(row.get(close_a))),
            ]
            seen = set()
            for selection, price in prices:
                if price is None or (selection, bookmaker, price) in seen:
                    continue
                seen.add((selection, bookmaker, price))
                key = (match_id, bookmaker, selection, price)
                if key in existing:
                    skipped += 1
                    continue
                save_odds_history(
                    match_id=match_id,
                    kickoff=kickoff,
                    league=league_name,
                    home_team=home,
                    away_team=away,
                    selection=selection,
                    bookmaker=bookmaker,
                    back_odds=price,
                    lay_odds=None,
                )
                existing.add(key)
                saved += 1

    return saved, skipped, linked


def download_csv(url):
    response = requests.get(url, timeout=45)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def collect_football_data_odds():
    existing = load_existing_odds()
    total_saved = 0
    total_skipped = 0
    total_linked = 0

    for season in season_codes():
        for div_code, league_name in MAIN_DIVISIONS.items():
            url = season_url(season, div_code)
            try:
                rows = download_csv(url)
            except Exception as exc:
                print(f"{url} failed: {exc}")
                continue
            if not rows:
                continue
            saved, skipped, linked = ingest_rows(rows, league_name, existing)
            print(
                f"{league_name} {season}: {len(rows)} matches, "
                f"+{saved} odds, linked {linked} historical"
            )
            total_saved += saved
            total_skipped += skipped
            total_linked += linked

    for url, league_name in EXTRA_FILES.items():
        try:
            rows = download_csv(url)
        except Exception as exc:
            print(f"{league_name} extra failed: {exc}")
            continue
        if not rows:
            print(f"{league_name}: extra file missing")
            continue
        saved, skipped, linked = ingest_rows(rows, league_name, existing)
        print(
            f"{league_name} extra: {len(rows)} matches, "
            f"+{saved} odds, linked {linked} historical"
        )
        total_saved += saved
        total_skipped += skipped
        total_linked += linked

    print(f"Saved {total_saved} odds_history rows")
    print(f"Filled {total_linked} historical_matches odd_h/odd_a gaps")
    print(f"Skipped {total_skipped} empty/duplicate rows")


if __name__ == "__main__":
    collect_football_data_odds()
