import sys
import time
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


def log_step(message):

    print(
        "\n"
        + "=" * 60
    )

    print(message)

    print(
        "=" * 60
    )


def log_progress(
    current,
    total
):

    pct = round(
        (
            current
            / total
        )
        * 100,
        1
    )

    print(
        f"Teams: "
        f"{current:,}/{total:,} "
        f"({pct}%)"
    )


def build_team_intelligence():

    start_time = time.time()

    log_step(
        "Building Historical Team Intelligence"
    )

    conn = get_db()

    print(
        "Loading teams..."
    )

    teams = conn.execute(
        """
        SELECT DISTINCT home_team
        FROM historical_matches

        UNION

        SELECT DISTINCT away_team
        FROM historical_matches
        """
    ).fetchall()

    total_teams = len(
        teams
    )

    print(
        f"{total_teams:,} teams found"
    )

    updated = 0

    for idx, row in enumerate(
        teams,
        start=1
    ):

        team = row[0]

        matches = conn.execute(
            """
            SELECT

                match_id,

                home_team,
                away_team,

                final_home,
                final_away

            FROM historical_matches

            WHERE home_team = ?
            OR away_team = ?
            """,
            (
                team,
                team
            )
        ).fetchall()

        match_count = len(
            matches
        )

        two_up_count = 0

        comeback_count = 0

        for match in matches:

            match_id = match[0]

            home_team = match[1]
            away_team = match[2]

            final_home = match[3]
            final_away = match[4]

            events = conn.execute(
                """
                SELECT

                    minute,

                    side,

                    is_goal

                FROM historical_events

                WHERE match_id = ?

                ORDER BY minute
                """,
                (
                    match_id,
                )
            ).fetchall()

            home_score = 0
            away_score = 0

            team_went_two_up = False

            for event in events:

                side = event[1]
                is_goal = event[2]

                if not is_goal:
                    continue

                if side == 1:
                    home_score += 1

                elif side == 2:
                    away_score += 1

                if team == home_team:

                    if (
                        home_score
                        -
                        away_score
                        >= 2
                    ):
                        team_went_two_up = True

                elif team == away_team:

                    if (
                        away_score
                        -
                        home_score
                        >= 2
                    ):
                        team_went_two_up = True

            if team_went_two_up:

                two_up_count += 1

                if team == home_team:

                    if (
                        final_home
                        <=
                        final_away
                    ):
                        comeback_count += 1

                elif team == away_team:

                    if (
                        final_away
                        <=
                        final_home
                    ):
                        comeback_count += 1

        turnaround_rate = 0


        if two_up_count > 0:

            turnaround_rate = round(
                (
                    comeback_count
                    /
                    two_up_count
                )
                * 100,
                2
            )

        historical_trigger_rate = 0

        if match_count > 0:

            historical_trigger_rate = round(
                (
                    two_up_count
                    /
                    match_count
                )
                * 100,
                2
            )

        conn.execute(

            """
            INSERT OR REPLACE
            INTO team_stats
            (
            team,

            historical_matches,

            historical_two_up,

            historical_comebacks,

            historical_turnaround_rate,

            historical_trigger_rate
            )


            VALUES
            (
                ?, ?, ?, ?, ?, ?
            )
            """,
            (
                team,

                match_count,

                two_up_count,

                comeback_count,

                turnaround_rate,

                historical_trigger_rate
            )
        )

        updated += 1

        if (
            idx % 25 == 0
            or idx == total_teams
        ):

            log_progress(
                idx,
                total_teams
            )

    conn.commit()

    conn.close()

    elapsed = round(
        time.time()
        -
        start_time,
        1
    )

    log_step(
        "Historical Team Intelligence Complete"
    )

    print(
        f"Teams Updated: {updated:,}"
    )

    print(
        f"Runtime: {elapsed}s"
    )

    print(
        "\n✅ Complete"
    )


if __name__ == "__main__":

    build_team_intelligence()
