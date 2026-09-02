import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(
        str(PROJECT_ROOT)
    )

from database import get_db


MATCH_FILE = (
    PROJECT_ROOT
    / "data"
    / "ginf.csv"
)

EVENT_FILE = (
    PROJECT_ROOT
    / "data"
    / "events.csv"
)


def import_matches():

    print(
        "Loading matches..."
    )

    df = pd.read_csv(
        MATCH_FILE
    )

    conn = get_db()

    conn.execute(
        """
        DELETE FROM
        historical_matches
        """
    )

    records = []

    for _, row in df.iterrows():

        records.append(
            (
                row["id_odsp"],

                str(
                    row["date"]
                ),

                str(
                    row["league"]
                ),

                str(
                    row["season"]
                ),

                str(
                    row["country"]
                ),

                str(
                    row["ht"]
                ),

                str(
                    row["at"]
                ),

                int(
                    row["fthg"]
                ),

                int(
                    row["ftag"]
                ),

                row["odd_h"],

                row["odd_d"],

                row["odd_a"]
            )
        )

    conn.executemany(
        """
        INSERT INTO
        historical_matches
        (
            match_id,

            date,

            league,
            season,

            country,

            home_team,
            away_team,

            final_home,
            final_away,

            odd_h,
            odd_d,
            odd_a
        )

        VALUES
        (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        records
    )

    conn.commit()
    conn.close()

    print(
        f"{len(records)} matches imported"
    )


def import_events():

    print(
        "Loading events..."
    )

    df = pd.read_csv(
        EVENT_FILE
    )

    conn = get_db()

    conn.execute(
        """
        DELETE FROM
        historical_events
        """
    )

    records = []

    for _, row in df.iterrows():

        records.append(
            (
                row["id_odsp"],

                row["time"],

                row["event_type"],

                row["event_type2"],

                row["side"],

                str(
                    row["event_team"]
                ),

                str(
                    row["player"]
                ),

                row["is_goal"],

                row["situation"]
            )
        )

    conn.executemany(
        """
        INSERT INTO
        historical_events
        (
            match_id,

            minute,

            event_type,

            event_type2,

            side,

            team,

            player,

            is_goal,

            situation
        )

        VALUES
        (
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        records
    )

    conn.commit()
    conn.close()

    print(
        f"{len(records)} events imported"
    )


def run():

    import_matches()

    import_events()

    print(
        "\n✅ Historical data imported."
    )


if __name__ == "__main__":

    run()

