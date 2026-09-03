from datetime import datetime, timezone

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
from team_normalizer import normalize_team


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

    return 0


def build_training_data():

    conn = get_db()

    conn.execute(
        """
        DELETE FROM training_data
        """
    )

    matches = conn.execute(
        """
        SELECT

            match_id,
            league,

            home_team,
            away_team,

            home_turnaround,
            away_turnaround,

            home_lead_minute,
            away_lead_minute

        FROM match_results
        """
    ).fetchall()

    inserted = 0

    for match in matches:

        (
            match_id,
            league,

            home_team,
            away_team,

            home_turnaround,
            away_turnaround,

            home_lead_minute,
            away_lead_minute
        ) = match

        home_team = normalize_team(
            home_team
        )

        away_team = normalize_team(
            away_team
        )

        home_stats = conn.execute(
            """
            SELECT

                avg_xg,
                avg_xga,

                goals_last5,
                conceded_last5,

                turnaround_pct,

                two_up_trigger_rate,

                historical_turnaround_rate,
                historical_trigger_rate,

                early_goal_rate,
                early_concede_rate,

                first_lead_rate,
                first_concede_rate,

                comeback_rate,

                lead_retention_rate,

                first_half_goal_diff,
                second_half_goal_diff,

                burnout_index,

                opponent_turnaround_rate

             FROM team_stats

             WHERE team = ?

            """,
            (
                home_team,
            )
        ).fetchone()

        away_stats = conn.execute(
            """
            SELECT

                avg_xg,
                avg_xga,

                goals_last5,
                conceded_last5,

                turnaround_pct,

                two_up_trigger_rate,

                historical_turnaround_rate,
                historical_trigger_rate,

                early_goal_rate,
                early_concede_rate,

                first_lead_rate,
                first_concede_rate,

                comeback_rate,

                lead_retention_rate,

                first_half_goal_diff,
                second_half_goal_diff,

                burnout_index,

                opponent_turnaround_rate

             FROM team_stats

             WHERE team = ?
            """,
            (
                away_team,
            )
        ).fetchone()

        if not home_stats:

            print(
                f"Missing home team: {home_team}"
            )

            continue

        if not away_stats:

            print(
                f"Missing away team: {away_team}"
            )

            continue

        league_turnaround_rate = (
            get_league_turnaround_rate(
                conn,
                league
            )
        )

        home_xg_edge = (
            (home_stats[0] or 0)
            -
            (home_stats[1] or 0)
        )

        away_xg_edge = (
            (away_stats[0] or 0)
            -
            (away_stats[1] or 0)
        )

        rows_to_insert = [

            (
                match_id,
                league,
                home_team,

                1,

                None,
                None,

                home_stats[0],
                home_stats[1],

                home_xg_edge,

                home_stats[2],
                home_stats[3],

                home_stats[4],

                home_stats[5],

                home_stats[6],
                home_stats[7],

                home_stats[8],
                home_stats[9],

                home_stats[10],
                home_stats[11],

                home_stats[12],

                home_stats[13],

                home_stats[14],
                home_stats[15],

                home_stats[16],

                league_turnaround_rate,
                away_stats[17],

                home_lead_minute or 0,

                2,

                None,
                None,

                None,
                None,

                None,
                None,

                1.0,

                home_turnaround,

                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            (
                match_id,
                league,
                away_team,

                0,

                None,
                None,

                away_stats[0],
                away_stats[1],

                away_xg_edge,

                away_stats[2],
                away_stats[3],

                away_stats[4],

                away_stats[5],

                away_stats[6],
                away_stats[7],

                away_stats[8],
                away_stats[9],

                away_stats[10],
                away_stats[11],

                away_stats[12],

                away_stats[13],

                away_stats[14],
                away_stats[15],

                away_stats[16],

                league_turnaround_rate,
                home_stats[17],

                away_lead_minute or 0,

                2,

                None,
                None,

                None,
                None,

                None,
                None,

                1.0,

                away_turnaround,

                datetime.now(
                    timezone.utc
                ).isoformat()
            )

        ]



        for row in rows_to_insert:

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

                    historical_turnaround_rate,
                    historical_trigger_rate,

                    early_goal_rate,
                    early_concede_rate,

                    first_lead_rate,
                    first_concede_rate,

                    comeback_rate,

                    lead_retention_rate,

                    first_half_goal_diff,
                    second_half_goal_diff,

                    burnout_index,


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
                row
            )

        inserted += 2

    conn.commit()
    conn.close()

    print(
        f"{inserted} training rows built"
    )


if __name__ == "__main__":

    build_training_data()
