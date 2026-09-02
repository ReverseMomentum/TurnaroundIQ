import pandas as pd

from datetime import (
    datetime,
    timezone
)

import sys
from pathlib import Path

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

CSV_FILE = (
    "data/2up_multi_league_dataset.csv"
)


def get_league_turnaround_rate(
    conn,
    league
):

    row = conn.execute(
        """
        SELECT turnaround_rate
        FROM league_stats
        WHERE league = ?
        """,
        (league,)
    ).fetchone()

    if row:
        return row[0]

    return None


def import_dataset():

    conn = get_db()

    df = pd.read_csv(
        CSV_FILE
    )

    inserted = 0

    for _, row in df.iterrows():

        triggered = bool(
            row["2up_triggered"]
        )

        comeback = bool(
            row["comeback_occurred"]
        )

        if not triggered:
            continue

        league = (
            row["league"]
            if "league" in row
            else "Historical"
        )

        league_turnaround_rate = (
            get_league_turnaround_rate(
                conn,
                league
            )
        )

        avg_xg = None
        avg_xga = None

        xg_edge = None

        if (
            avg_xg is not None
            and
            avg_xga is not None
        ):
            xg_edge = (
                avg_xg -
                avg_xga
            )

        conn.execute(
            """
            INSERT INTO training_data
            (

                match_id,

                league,
                team,

                is_home,

                back_odds,
                lay_odds,

                avg_xg,
                avg_xga,

                xg_edge,

                goals_last5,
                conceded_last5,

                turnaround_pct,

                two_up_trigger_rate,

                historical_turnaround_rate,

                league_turnaround_rate,

                opponent_turnaround_rate,

                lead_minute,
                max_lead,

                opening_back_odds,
                odds_movement,

                red_cards_for,
                red_cards_against,

                shots_for,
                shots_against,

                sample_weight,

                full_turnaround,

                created_at

            )

            VALUES
            (

                ?, ?, ?,

                ?,

                ?, ?,

                ?, ?,

                ?,

                ?, ?,

                ?,

                ?,

                ?,

                ?,

                ?,

                ?, ?,

                ?, ?,

                ?, ?,

                ?, ?,

                ?,

                ?,

                ?

            )
            """,
            (

                f"csv_{inserted}",

                league,

                row["trigger_team"],

                None,

                None,
                None,

                avg_xg,
                avg_xga,

                xg_edge,

                None,
                None,

                None,

                None,

                None,

                league_turnaround_rate,

                None,

                None,

                2,

                None,
                None,

                None,
                None,

                None,
                None,

                0.50,

                int(comeback),

                datetime.now(
                    timezone.utc
                ).isoformat()

            )
        )

        inserted += 1

    conn.commit()

    conn.close()

    print(
        f"{inserted} historical rows imported"
    )


if __name__ == "__main__":

    import_dataset()
