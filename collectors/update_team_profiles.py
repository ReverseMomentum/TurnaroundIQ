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


def update_team_profiles():

    conn = get_db()

    teams = conn.execute(
        """
        SELECT DISTINCT home_team
        FROM match_results

        UNION

        SELECT DISTINCT away_team
        FROM match_results
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

        for trigger, turnaround in home_rows:

            if trigger:

                two_up_leads += 1

                if turnaround:

                    failed_leads += 1

        for trigger, turnaround in away_rows:

            if trigger:

                two_up_leads += 1

                if turnaround:

                    failed_leads += 1

        two_up_trigger_rate = 0

        if matches_played > 0:

            two_up_trigger_rate = round(
                (
                    two_up_leads
                    /
                    matches_played
                )
                * 100,
                2
            )

        lead_retention_rate = 100

        if two_up_leads > 0:

            lead_retention_rate = round(
                (
                    (
                        two_up_leads
                        -
                        failed_leads
                    )
                    /
                    two_up_leads
                )
                * 100,
                2
            )

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

        conn.execute(
            """
            UPDATE team_stats

            SET

                matches_played = ?,

                two_up_leads = ?,

                failed_leads = ?,

                two_up_trigger_rate = ?,

                turnaround_pct = ?,

                lead_retention_rate = ?,

                updated_at = ?

            WHERE team = ?
            """,
            (
                matches_played,

                two_up_leads,

                failed_leads,

                two_up_trigger_rate,

                turnaround_pct,

                lead_retention_rate,

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
        f"{updated} team profiles updated"
    )


if __name__ == "__main__":

    update_team_profiles()
