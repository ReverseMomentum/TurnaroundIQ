"""
Free xG trial from Understat-derived public aggregates (no API key).

Source (community mirror of understat.com team-season stats):
  https://github.com/vibedatascience/understat_teams_aggregated

    python -u collectors/understat_xg_trial.py
    python -u collectors/understat_xg_trial.py --season 2025
    python -u collectors/understat_xg_trial.py --dry-run

Writes avg_xg / avg_xga / xg_edge into team_stats for matched teams.
Big-5 + RFPL only (Understat coverage).
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db
from team_normalizer import normalize_team

# Prefer current-season file; fall back to full history
CSV_CURRENT = (
    "https://raw.githubusercontent.com/vibedatascience/understat_teams_aggregated/"
    "main/understat_teams_aggregated_2025_latest.csv"
)
CSV_FULL = (
    "https://raw.githubusercontent.com/vibedatascience/understat_teams_aggregated/"
    "main/understat_teams_aggregated_2014_td.csv"
)

# Column name variants seen across exports
XG_COLS = ("xG", "xg", "xg_for")
XGA_COLS = ("xGA", "xga", "xg_against")
TEAM_COLS = ("team", "team_name", "Team", "title")
GAMES_COLS = ("games", "games_played", "GP", "matches")
SEASON_COLS = ("season", "Season", "year")
LEAGUE_COLS = ("league", "League", "competition")


def _pick(row, names):
    for n in names:
        if n in row and pd.notna(row[n]):
            return row[n]
    return None


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_csv(url: str) -> pd.DataFrame:
    print(f"Fetching {url}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def _season_key(val) -> str:
    s = str(val)
    # "2025/2026" or "2025" or 2025
    if "/" in s:
        return s.split("/")[0].strip()
    return s[:4]


def load_understat(season: str | None) -> pd.DataFrame:
    try:
        df = _load_csv(CSV_CURRENT)
        source = "current"
    except Exception as exc:
        print(f"[WARN] current CSV failed ({exc}) — trying full history")
        df = _load_csv(CSV_FULL)
        source = "full"

    print(f"Loaded {len(df)} rows from {source} export")
    print(f"Columns: {list(df.columns)[:12]}…")

    # Normalise season filter if present
    season_col = next((c for c in SEASON_COLS if c in df.columns), None)
    if season and season_col:
        before = len(df)
        df = df[df[season_col].map(_season_key) == str(season)[:4]]
        print(f"Season filter {season}: {before} → {len(df)} rows")
    elif season_col and source == "full":
        # Default to latest season in file
        keys = sorted(df[season_col].map(_season_key).unique())
        latest = keys[-1] if keys else None
        if latest:
            df = df[df[season_col].map(_season_key) == latest]
            print(f"Using latest season key {latest}: {len(df)} rows")

    return df


def apply_to_team_stats(df: pd.DataFrame, dry_run: bool = False) -> dict:
    team_col = next((c for c in TEAM_COLS if c in df.columns), None)
    if not team_col:
        raise RuntimeError(f"No team column in {list(df.columns)}")

    updated = matched = skipped = 0
    now = datetime.now(timezone.utc).isoformat()
    rows_out = []

    for _, row in df.iterrows():
        raw_name = _pick(row, TEAM_COLS)
        if not raw_name:
            skipped += 1
            continue
        team = normalize_team(str(raw_name))
        if not team:
            skipped += 1
            continue

        xg = _to_float(_pick(row, XG_COLS))
        xga = _to_float(_pick(row, XGA_COLS))
        games = _to_float(_pick(row, GAMES_COLS)) or 0.0

        # CSV is season totals — convert to per-match for model scale
        if games and games > 0 and xg is not None:
            avg_xg = round(xg / games, 3)
        else:
            avg_xg = xg
        if games and games > 0 and xga is not None:
            avg_xga = round(xga / games, 3)
        else:
            avg_xga = xga

        if avg_xg is None and avg_xga is None:
            skipped += 1
            continue

        xg_edge = None
        if avg_xg is not None and avg_xga is not None:
            xg_edge = round(avg_xg - avg_xga, 3)

        matched += 1
        rows_out.append((team, avg_xg, avg_xga, xg_edge, games))

        if dry_run:
            continue

        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
        conn.execute(
            """
            UPDATE team_stats
            SET avg_xg = ?,
                avg_xga = ?,
                xg_edge = ?,
                updated_at = ?
            WHERE team = ?
            """,
            (avg_xg, avg_xga, xg_edge, now, team),
        )
        conn.commit()
        conn.close()
        updated += 1

    # Coverage vs existing team_stats
    conn = get_db()
    total_teams = conn.execute("SELECT COUNT(*) FROM team_stats").fetchone()[0]
    with_xg = conn.execute(
        "SELECT COUNT(*) FROM team_stats WHERE avg_xg IS NOT NULL"
    ).fetchone()[0]
    conn.close()

    print(f"Matched rows: {matched}  written: {updated}  skipped: {skipped}")
    print(f"team_stats with avg_xg: {with_xg}/{total_teams}")
    if dry_run and rows_out[:8]:
        print("Sample (dry-run):")
        for t, xg, xga, edge, g in rows_out[:8]:
            print(f"  {t}: xG/90≈{xg}  xGA/90≈{xga}  edge={edge}  games={g}")

    return {
        "matched": matched,
        "updated": updated,
        "with_xg": with_xg,
        "total_teams": total_teams,
    }


def main():
    parser = argparse.ArgumentParser(description="Understat free xG trial")
    parser.add_argument(
        "--season",
        default="2025",
        help="Season start year (Understat style), e.g. 2025 for 2025/26",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and show sample without writing team_stats",
    )
    args = parser.parse_args()

    df = load_understat(args.season)
    if df.empty:
        print("No rows after filter — try --season 2024 or omit filter")
        return
    apply_to_team_stats(df, dry_run=args.dry_run)
    if not args.dry_run:
        print("\nNext: rebuild training + ablation")
        print("  python -u training/build_training_data.py")
        print("  python -u models/xg_ablation.py")


if __name__ == "__main__":
    main()
