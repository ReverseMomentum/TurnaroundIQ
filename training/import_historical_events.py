"""
Import historical CSVs into historical_matches / historical_events.

    python -u training/import_historical_events.py                     # api-sports first, older CSVs fill gaps
    python -u training/import_historical_events.py --source apisports  # api-sports backfill only
    python -u training/import_historical_events.py --source fbref      # legacy FBref CSVs only
    python -u training/import_historical_events.py --allow-shrink        # accept fewer matches than now

The same fixture from two sources is imported once (api-sports wins), so
profiles never double-count a match. The import refuses to replace
historical_matches with a much smaller set (e.g. a half-finished backfill)
unless --allow-shrink is passed.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db
from team_normalizer import normalize_team

DATA_DIR = PROJECT_ROOT / "data"
# Order = priority when the same fixture appears in more than one source.
SOURCES = {
    "apisports": (["ginf_apisports.csv"], ["events_apisports.csv"]),
    # Older one-off backfills (api-sports single seasons / TheStatsAPI).
    "legacy_api": (["ginf_api.csv"], ["events_api.csv"]),
    "fbref": (["ginf.csv"], ["events.csv"]),
}
MIN_KEEP_RATIO = 0.8

SOURCES["all"] = tuple(
    sum((SOURCES[k][i] for k in ("apisports", "legacy_api", "fbref")), [])
    for i in (0, 1)
)


def load_named(names):
    frames = []
    for name in names:
        path = DATA_DIR / name
        if not path.exists():
            print(f"Skip missing {name}")
            continue
        print(f"Reading {name}")
        frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError(f"None of {names} exist in data/")
    return pd.concat(frames, ignore_index=True)


def dedupe_matches(df):
    """Drop repeated ids, then the same fixture (date + teams) from a lower-priority source."""
    df = df.drop_duplicates(subset=["id_odsp"], keep="first").copy()
    df["_ht"] = df["ht"].astype(str).map(normalize_team)
    df["_at"] = df["at"].astype(str).map(normalize_team)
    df["_date"] = df["date"].astype(str).str[:10]
    before = len(df)
    df = df.drop_duplicates(subset=["_date", "_ht", "_at"], keep="first")
    dropped = before - len(df)
    if dropped:
        print(f"{dropped} cross-source duplicate fixtures dropped")
    return df.drop(columns=["_ht", "_at", "_date"])


def current_match_count(conn):
    try:
        return conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0]
    except Exception:
        return 0


def import_matches(source="all", allow_shrink=False):
    print("Loading matches...")
    df = dedupe_matches(load_named(SOURCES[source][0]))
    conn = get_db()
    existing = current_match_count(conn)
    if not allow_shrink and existing and len(df) < existing * MIN_KEEP_RATIO:
        conn.close()
        print(
            f"Refusing to import: {len(df)} matches would replace {existing} "
            f"(< {int(MIN_KEEP_RATIO * 100)}%). Keep collecting, or pass --allow-shrink."
        )
        raise SystemExit(4)
    conn.execute("DELETE FROM historical_matches")
    records = []
    for _, row in df.iterrows():
        records.append(
            (
                str(row["id_odsp"]),
                str(row.get("date", "")),
                str(row.get("league", "")),
                str(row.get("season", "")),
                str(row.get("country", "")),
                normalize_team(str(row["ht"])),
                normalize_team(str(row["at"])),
                None if pd.isna(row.get("fthg")) else int(row["fthg"]),
                None if pd.isna(row.get("ftag")) else int(row["ftag"]),
                None if pd.isna(row.get("odd_h")) else row.get("odd_h"),
                None if pd.isna(row.get("odd_d")) else row.get("odd_d"),
                None if pd.isna(row.get("odd_a")) else row.get("odd_a"),
            )
        )
    conn.executemany(
        """
        INSERT INTO historical_matches (
            match_id, date, league, season, country,
            home_team, away_team, final_home, final_away,
            odd_h, odd_d, odd_a
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )
    conn.commit()
    conn.close()
    print(f"{len(records)} matches imported")
    return {str(i) for i in df["id_odsp"]}


def import_events(source="all", match_ids=None):
    print("Loading events...")
    try:
        df = load_named(SOURCES[source][1])
    except FileNotFoundError:
        print("No events files")
        return
    df["id_odsp"] = df["id_odsp"].astype(str)
    if match_ids is not None:
        df = df[df["id_odsp"].isin(match_ids)]
    # A re-fetched match may have appended its goals twice.
    df = df.drop_duplicates(subset=["id_odsp", "time", "side", "player", "is_goal"])
    conn = get_db()
    conn.execute("DELETE FROM historical_events")
    records = []
    for _, row in df.iterrows():
        side = row.get("side")
        if pd.isna(side):
            continue
        records.append(
            (
                str(row["id_odsp"]),
                None if pd.isna(row.get("time")) else int(row["time"]),
                row.get("event_type"),
                row.get("event_type2"),
                int(side),
                normalize_team(str(row.get("event_team", ""))),
                str(row.get("player", "")),
                0 if pd.isna(row.get("is_goal")) else int(row.get("is_goal")),
                row.get("situation"),
            )
        )
    conn.executemany(
        """
        INSERT INTO historical_events (
            match_id, minute, event_type, event_type2, side,
            team, player, is_goal, situation
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )
    conn.commit()
    conn.close()
    print(f"{len(records)} events imported")


def run(source="all", allow_shrink=False):
    match_ids = import_matches(source, allow_shrink)
    import_events(source, match_ids)
    print("\nHistorical data imported.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=sorted(SOURCES), default="all")
    parser.add_argument("--allow-shrink", action="store_true")
    args = parser.parse_args()
    run(args.source, args.allow_shrink)
