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


def pct(
    numerator,
    denominator
):

    if denominator <= 0:
        return 0

    return round(
        (numerator / denominator) * 100,
        2
    )


def update_live_team_stats():

    conn = get_db()

    teams = conn.execute(
        """
        SELECT DISTINCT team
        FROM team_stats
        """
    ).fetchall()

    updated = 0

    for row in teams:

        team = row[0]

        home_rows = conn.execute(
            """
            SELECT

                home_2up,
                home_turnaround,

                home_early_goal,
                home_early_concede,

                home_first_lead,
                home_first_concede,

                home_led,

                home_first_half_for,
                home_first_half_against,
                home_second_half_for,
                home_second_half_against,

                final_home,
                final_away

            FROM match_results

            WHERE home_team = ?
            """,
            (team,)
        ).fetchall()

        away_rows = conn.execute(
            """
            SELECT

                away_2up,
                away_turnaround,

                away_early_goal,
                away_early_concede,

                away_first_lead,
                away_first_concede,

                away_led,

                away_first_half_for,
                away_first_half_against,
                away_second_half_for,
                away_second_half_against,

                final_away,
                final_home

            FROM match_results

            WHERE away_team = ?
            """,
            (team,)
        ).fetchall()

        matches_played = (
            len(home_rows) + len(away_rows)
        )

        if matches_played == 0:

            continue

        two_up_leads = 0
        comeback_attempts = 0
        successful_comebacks = 0

        early_goals = 0
        early_concedes = 0

        first_leads = 0
        first_concedes = 0

        lead_games = 0
        retained_leads = 0

        half_diff_sum = 0
        second_half_diff_sum = 0

        for (
            trigger, turnaround,
            early_goal, early_concede,
            first_lead, first_concede,
            led,
            fh_for, fh_against,
            sh_for, sh_against,
            team_final, opp_final
        ) in (
            list(home_rows) + list(away_rows)
        ):

            if trigger:
                two_up_leads += 1

            if first_concede:

                comeback_attempts += 1

                if (team_final or 0) >= (opp_final or 0):

                    successful_comebacks += 1

            if early_goal:
                early_goals += 1

            if early_concede:
                early_concedes += 1

            if first_lead:
                first_leads += 1

            if first_concede:
                first_concedes += 1

            if led:

                lead_games += 1

                if (team_final or 0) > (opp_final or 0):

                    retained_leads += 1

            half_diff_sum += (
                (fh_for or 0) - (fh_against or 0)
            )

            second_half_diff_sum += (
                (sh_for or 0) - (sh_against or 0)
            )

        live_trigger_rate = pct(
            two_up_leads,
            matches_played
        )

        live_early_goal_rate = pct(
            early_goals,
            matches_played
        )

        live_early_concede_rate = pct(
            early_concedes,
            matches_played
        )

        live_first_lead_rate = pct(
            first_leads,
            matches_played
        )

        live_first_concede_rate = pct(
            first_concedes,
            matches_played
        )

        live_comeback_rate = pct(
            successful_comebacks,
            comeback_attempts
        )

        live_lead_retention_rate = pct(
            retained_leads,
            lead_games
        )

        live_first_half_goal_diff = round(
            half_diff_sum / matches_played,
            3
        )

        live_second_half_goal_diff = round(
            second_half_diff_sum / matches_played,
            3
        )

        # ------------------------------------
        # Pull historical baseline to diff against
        # ------------------------------------

        existing = conn.execute(
            """
            SELECT

                historical_trigger_rate,

                early_goal_rate,
                early_concede_rate,

                first_lead_rate,
                first_concede_rate,

                comeback_rate,

                lead_retention_rate,

                burnout_index

            FROM team_stats

            WHERE team = ?
            """,
            (team,)
        ).fetchone()

        (
            historical_trigger_rate,
            early_goal_rate,
            early_concede_rate,
            first_lead_rate,
            first_concede_rate,
            comeback_rate,
            lead_retention_rate,
            burnout_index
        ) = (
            existing
            if existing
            else (0, 0, 0, 0, 0, 0, 0, 0)
        )

        historical_trigger_rate = historical_trigger_rate or 0
        early_goal_rate = early_goal_rate or 0
        early_concede_rate = early_concede_rate or 0
        first_lead_rate = first_lead_rate or 0
        first_concede_rate = first_concede_rate or 0
        comeback_rate = comeback_rate or 0
        lead_retention_rate = lead_retention_rate or 0
        burnout_index = burnout_index or 0

        live_burnout_index = round(
            (
                live_early_goal_rate
                *
                (100 - live_lead_retention_rate)
                *
                live_trigger_rate
            )
            / 10000,
            2
        )

        trigger_rate_delta = round(
            live_trigger_rate - historical_trigger_rate,
            2
        )

        early_goal_delta = round(
            live_early_goal_rate - early_goal_rate,
            2
        )

        early_concede_delta = round(
            live_early_concede_rate - early_concede_rate,
            2
        )

        first_lead_delta = round(
            live_first_lead_rate - first_lead_rate,
            2
        )

        first_concede_delta = round(
            live_first_concede_rate - first_concede_rate,
            2
        )

        comeback_delta = round(
            live_comeback_rate - comeback_rate,
            2
        )

        lead_retention_delta = round(
            live_lead_retention_rate - lead_retention_rate,
            2
        )

        burnout_delta = round(
            live_burnout_index - burnout_index,
            2
        )

        abs_trigger_delta = abs(
            trigger_rate_delta
        )

        abs_retention_delta = abs(
            lead_retention_delta
        )

        conn.execute(
            """
            UPDATE team_stats

            SET

                live_trigger_rate = ?,
                live_early_goal_rate = ?,
                live_early_concede_rate = ?,
                live_first_lead_rate = ?,
                live_first_concede_rate = ?,
                live_comeback_rate = ?,
                live_lead_retention_rate = ?,
                live_first_half_goal_diff = ?,
                live_second_half_goal_diff = ?,
                live_burnout_index = ?,

                trigger_rate_delta = ?,
                early_goal_delta = ?,
                early_concede_delta = ?,
                first_lead_delta = ?,
                first_concede_delta = ?,
                comeback_delta = ?,
                lead_retention_delta = ?,
                burnout_delta = ?,

                abs_trigger_delta = ?,
                abs_retention_delta = ?,

                updated_at = ?

            WHERE team = ?
            """,
            (
                live_trigger_rate,
                live_early_goal_rate,
                live_early_concede_rate,
                live_first_lead_rate,
                live_first_concede_rate,
                live_comeback_rate,
                live_lead_retention_rate,
                live_first_half_goal_diff,
                live_second_half_goal_diff,
                live_burnout_index,

                trigger_rate_delta,
                early_goal_delta,
                early_concede_delta,
                first_lead_delta,
                first_concede_delta,
                comeback_delta,
                lead_retention_delta,
                burnout_delta,

                abs_trigger_delta,
                abs_retention_delta,

                datetime.now(
                    timezone.utc
                ).isoformat(),

                team
            )
        )

        updated += 1

    conn.commit()
    conn.close()

    print(
        f"{updated} teams updated with live + divergence stats"
    )


if __name__ == "__main__":

    update_live_team_stats()
