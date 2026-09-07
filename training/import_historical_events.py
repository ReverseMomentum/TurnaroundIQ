import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db
from team_normalizer import normalize_team

DATA_DIR = PROJECT_ROOT / "data"
MATCH_FILES = ["ginf.csv", "ginf_api.csv"]
EVENT_FILES = ["events.csv", "events_api.csv"]


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


def import_matches():
    print("Loading matches...")
    df = load_named(MATCH_FILES)
    df = df.drop_duplicates(subset=["id_odsp"], keep="first")
    conn = get_db()
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


def import_events():
    print("Loading events...")
    try:
        df = load_named(EVENT_FILES)
    except FileNotFoundError:
        print("No events files")
        return
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


def run():
    import_matches()
    import_events()
    print("\nHistorical data imported.")


if __name__ == "__main__":
    run()
