import sys
from pathlib import Path

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(
        str(PROJECT_ROOT)
    )

from database import get_db


# Per-match raw behavioural columns, home + away
MATCH_RESULTS_COLUMNS = [

    "home_early_goal INTEGER",
    "home_early_concede INTEGER",
    "away_early_goal INTEGER",
    "away_early_concede INTEGER",

    "home_first_lead INTEGER",
    "home_first_concede INTEGER",
    "away_first_lead INTEGER",
    "away_first_concede INTEGER",

    "home_led INTEGER",
    "away_led INTEGER",

    "home_first_half_for INTEGER",
    "home_first_half_against INTEGER",
    "home_second_half_for INTEGER",
    "home_second_half_against INTEGER",

    "away_first_half_for INTEGER",
    "away_first_half_against INTEGER",
    "away_second_half_for INTEGER",
    "away_second_half_against INTEGER"
]

# Team-level aggregated "live" rates + divergence vs historical
TEAM_STATS_COLUMNS = [

    "live_trigger_rate REAL",
    "live_early_goal_rate REAL",
    "live_early_concede_rate REAL",
    "live_first_lead_rate REAL",
    "live_first_concede_rate REAL",
    "live_comeback_rate REAL",
    "live_lead_retention_rate REAL",
    "live_first_half_goal_diff REAL",
    "live_second_half_goal_diff REAL",
    "live_burnout_index REAL",

    "trigger_rate_delta REAL",
    "early_goal_delta REAL",
    "early_concede_delta REAL",
    "first_lead_delta REAL",
    "first_concede_delta REAL",
    "comeback_delta REAL",
    "lead_retention_delta REAL",
    "burnout_delta REAL",

    "abs_trigger_delta REAL",
    "abs_retention_delta REAL"
]

# training_data needs the same live/delta columns so they
# can actually reach the model
TRAINING_DATA_COLUMNS = TEAM_STATS_COLUMNS


def add_columns(
    conn,
    table,
    columns
):

    added = 0
    skipped = 0

    for col_def in columns:

        col_name = col_def.split()[0]

        try:

            conn.execute(
                f"ALTER TABLE {table} "
                f"ADD COLUMN {col_def}"
            )

            added += 1

        except Exception as exc:

            if "duplicate column" in str(exc).lower():

                skipped += 1

            else:

                print(
                    f"[ERROR] {table}.{col_name}: {exc}"
                )

    print(
        f"{table}: {added} columns added, "
        f"{skipped} already existed"
    )


def run_migration():

    conn = get_db()

    add_columns(
        conn,
        "match_results",
        MATCH_RESULTS_COLUMNS
    )

    add_columns(
        conn,
        "team_stats",
        TEAM_STATS_COLUMNS
    )

    add_columns(
        conn,
        "training_data",
        TRAINING_DATA_COLUMNS
    )

    conn.commit()
    conn.close()

    print(
        "\n✅ Migration complete."
    )


if __name__ == "__main__":

    run_migration()
