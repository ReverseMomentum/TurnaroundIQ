from datetime import (
    datetime,
    timezone
)

import sys
from pathlib import Path

sys.path.append(
    str(
        Path(__file__).resolve().parent.parent
    )
)

from database import get_db


def update_turnaround_stats():

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
                home_turnaround

            FROM match_results

            WHERE home_team = ?
            """,
            (team,)
        ).fetchall()

        away_rows = conn.execute(
            """
            SELECT

                away_2up,
                away_turnaround

            FROM match_results

            WHERE away_team = ?
            """,
            (team,)
        ).fetchall()

        matches_played = (
            len(home_rows)
            +
            len(away_rows)
        )

        two_up_leads = 0
        failed_leads = 0

        home_leads = 0
        home_failures = 0

        away_leads = 0
        away_failures = 0

        opponent_failures = []
        opponent_leads = []

        for trigger, turnaround in home_rows:

            if trigger:

                two_up_leads += 1

                home_leads += 1

                if turnaround:

                    failed_leads += 1

                    home_failures += 1

        for trigger, turnaround in away_rows:

            if trigger:

                two_up_leads += 1

                away_leads += 1

                if turnaround:

                    failed_leads += 1

                    away_failures += 1

        turnaround_pct = 0

        if two_up_leads > 0:

            turnaround_pct = round(
                (
                    failed_leads
                    /
                    two_up_leads
                )
                * 100,
                2
            )

        home_turnaround_pct = 0

        if home_leads > 0:

            home_turnaround_pct = round(
                (
                    home_failures
                    /
                    home_leads
                )
                * 100,
                2
            )

        away_turnaround_pct = 0

        if away_leads > 0:

            away_turnaround_pct = round(
                (
                    away_failures
                    /
                    away_leads
                )
                * 100,
                2
            )

        opponent_rows = conn.execute(
            """
            SELECT

                turnaround_pct

            FROM team_stats

            WHERE team != ?

            AND turnaround_pct IS NOT NULL
            """
            ,
            (team,)
        ).fetchall()

        opponent_turnaround_rate = 0

        if opponent_rows:

            rates = [
                r[0]
                for r in opponent_rows
                if r[0] is not None
            ]

            if rates:

                opponent_turnaround_rate = round(
                    sum(rates)
                    / len(rates),
                    2
                )

        conn.execute(
            """
            UPDATE team_stats

            SET

                matches_played = ?,

                two_up_leads = ?,

                failed_leads = ?,

                turnaround_pct = ?,

                home_turnaround_pct = ?,

                away_turnaround_pct = ?,

                opponent_turnaround_rate = ?,

                updated_at = ?

            WHERE team = ?
            """,
            (
                matches_played,

                two_up_leads,

                failed_leads,

                turnaround_pct,

                home_turnaround_pct,

                away_turnaround_pct,

                opponent_turnaround_rate,

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
        f"{updated} team statistics updated"
    )


if __name__ == "__main__":

    update_turnaround_stats()
