#!/usr/bin/env python3
"""
Free historical 1X2 odds from football-data.co.uk, linked to historical_matches.

    python -u collectors/odds_history_fd.py              # download (cached) + link
    python -u collectors/odds_history_fd.py --no-download

Purpose: test whether pre-match odds improve the FTA path model before paying
for a live odds feed (see `run.py odds-test`).

- CSVs are cached in data/football_data/; finished seasons are downloaded once.
- Each row is linked to an api-sports match by league + date (±1 day) + fuzzy
  team names (football-data says "Man United", api-sports "Manchester United").
- Odds: market average pre-match (AvgH/D/A), else Bet365, else Pinnacle; the
  "extra" league files only publish closing odds (AvgCH/D/A), used as-is.
- Stored in match_odds (own table — the historical import rebuilds
  historical_matches, so odds are kept separately).
"""

import argparse
import csv
import io
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import get_db
from team_normalizer import match_key, normalize_team

FIRST_SEASON = 2020
CACHE = PROJECT_ROOT / "data" / "football_data"
BASE = "https://www.football-data.co.uk"

MAIN_DIVISIONS = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One",
    "E3": "League Two", "SC0": "Premiership", "D1": "Bundesliga",
    "D2": "2. Bundesliga", "SP1": "La Liga", "I1": "Serie A", "I2": "Serie B",
    "F1": "Ligue 1", "F2": "Ligue 2", "N1": "Eredivisie",
    "B1": "Jupiler Pro League", "P1": "Primeira Liga", "T1": "Super Lig",
}
EXTRA_FILES = {
    "USA": "Major League Soccer", "DNK": "Superliga", "NOR": "Eliteserien",
    "SWE": "Allsvenskan", "IRL": "Premier Division", "AUT": "Austrian Bundesliga",
    "SWZ": "Swiss Super League", "RUS": "Russian Premier League", "BRA": "Brasileirao",
}
PRICE_SETS = [
    ("avg", "AvgH", "AvgD", "AvgA"),
    ("avg_old", "BbAvH", "BbAvD", "BbAvA"),
    ("b365", "B365H", "B365D", "B365A"),
    ("pinnacle", "PSH", "PSD", "PSA"),
    ("avg_close", "AvgCH", "AvgCD", "AvgCA"),
    ("pinnacle_close", "PSCH", "PSCD", "PSCA"),
]

DDL = """
CREATE TABLE IF NOT EXISTS match_odds (
    match_id TEXT PRIMARY KEY,
    odds_h REAL, odds_d REAL, odds_a REAL,
    source TEXT, fd_home TEXT, fd_away TEXT, match_score REAL
)
"""


def season_codes():
    now = datetime.utcnow()
    last = now.year if now.month >= 7 else now.year - 1
    return [(y, f"{y % 100:02d}{(y + 1) % 100:02d}") for y in range(FIRST_SEASON, last + 1)]


def fetch(url, path, refresh):
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            text = resp.content.decode("utf-8-sig", errors="replace")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            time.sleep(1)
            return text
        except requests.RequestException as exc:
            print(f"  {url}: {exc} (retry {attempt + 1})")
            time.sleep(5 * (attempt + 1))
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def parse_date(raw):
    raw = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _f(v):
    try:
        x = float(str(v).strip())
        return x if x > 1.0 else None
    except (TypeError, ValueError):
        return None


def pick_prices(row):
    for name, h, d, a in PRICE_SETS:
        oh, od, oa = _f(row.get(h)), _f(row.get(d)), _f(row.get(a))
        if oh and od and oa:
            return name, oh, od, oa
    return None


def download_rows(refresh_current=True, no_download=False):
    """Yield (league, date, home_raw, away_raw, source, oh, od, oa)."""
    jobs = []
    seasons = season_codes()
    current_code = seasons[-1][1]
    for _year, code in seasons:
        for div, league in MAIN_DIVISIONS.items():
            jobs.append((f"{BASE}/mmz4281/{code}/{div}.csv",
                         CACHE / f"{code}_{div}.csv", league,
                         refresh_current and code == current_code))
    for code, league in EXTRA_FILES.items():
        jobs.append((f"{BASE}/new/{code}.csv", CACHE / f"new_{code}.csv", league, refresh_current))

    for url, path, league, refresh in jobs:
        if no_download:
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        else:
            text = fetch(url, path, refresh)
        if not text:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            d = parse_date(row.get("Date"))
            if d is None or d.year < FIRST_SEASON:
                continue
            home = row.get("HomeTeam") or row.get("Home") or ""
            away = row.get("AwayTeam") or row.get("Away") or ""
            prices = pick_prices(row)
            if home and away and prices:
                yield (league, d, home, away) + prices


def _sim(a, b):
    ka, kb = match_key(normalize_team(a)), match_key(normalize_team(b))
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka in kb or kb in ka:
        return 0.9
    return SequenceMatcher(None, ka, kb).ratio()


def link(conn, rows):
    """Link football-data rows to historical_matches; returns per-league stats."""
    index = defaultdict(list)  # (league, day) -> [(match_id, home, away)]
    for mid, d, league, home, away in conn.execute(
        "SELECT match_id, date, league, home_team, away_team FROM historical_matches"
    ):
        try:
            day = date.fromisoformat(str(d)[:10]).toordinal()
        except ValueError:
            continue
        index[(league, day)].append((mid, home, away))

    stats = defaultdict(lambda: {"rows": 0, "linked": 0})
    taken = set()
    out = []
    for league, d, home, away, source, oh, od, oa in rows:
        stats[league]["rows"] += 1
        best = None
        for delta in (0, -1, 1):
            for mid, h, a in index.get((league, d.toordinal() + delta), []):
                if mid in taken:
                    continue
                sh, sa = _sim(home, h), _sim(away, a)
                score = sh + sa - 0.05 * abs(delta)
                if min(sh, sa) >= 0.5 and score >= 1.3 and (best is None or score > best[0]):
                    best = (score, mid)
        if best:
            taken.add(best[1])
            stats[league]["linked"] += 1
            out.append((best[1], oh, od, oa, source, home, away, round(best[0], 3)))
    conn.execute(DDL)
    conn.execute("DELETE FROM match_odds")
    conn.executemany("INSERT OR REPLACE INTO match_odds VALUES (?,?,?,?,?,?,?,?)", out)
    conn.commit()
    return stats, len(out)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-download", action="store_true", help="Use cached CSVs only")
    args = parser.parse_args(argv)
    rows = list(download_rows(no_download=args.no_download))
    print(f"{len(rows)} football-data rows with odds since {FIRST_SEASON}")
    conn = get_db()
    total_hist = conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0]
    stats, n = link(conn, rows)
    conn.close()
    print(f"\nLinked {n} of {total_hist} historical matches "
          f"({100 * n / max(total_hist, 1):.0f}%)")
    print("  league                    fd rows  linked")
    for league in sorted(stats):
        s = stats[league]
        pct = 100 * s["linked"] / max(s["rows"], 1)
        flag = "  <- check team names" if pct < 85 else ""
        print(f"  {league:<24} {s['rows']:>7}  {pct:>5.0f}%{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
