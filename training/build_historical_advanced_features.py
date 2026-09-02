import sys
import time
from pathlib import Path
from collections import defaultdict

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


def log_step(
    current,
    total,
    message
):

    print(
        "\n" +
        "=" * 60
    )

    print(
        f"Step {current}/{total} - {message}"
    )

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


def build_advanced_features():

    start_time = time.time()

    conn = get_db()

    log_step(
        1,
        4,
        "Loading Historical Matches"
    )

    matches = conn.execute(
        """
        SELECT
            match_id,
            home_team,
            away_team,
            final_home,
            final_away
        FROM historical_matches
        """
    ).fetchall()

    print(
        f"{len(matches):,} matches loaded"
    )

    log_step(
        2,
        4,
        "Loading Goal Events"
    )

    events = conn.execute(
        """
        SELECT
            match_id,
            minute,
            side,
            is_goal
        FROM historical_events
        WHERE is_goal = 1
        ORDER BY match_id, minute
        """
    ).fetchall()

    print(
        f"{len(events):,} goal events loaded"
    )

    events_by_match = defaultdict(list)

    for event in events:

        events_by_match[
            event[0]
        ].append(
            event
        )

    log_step(
        3,
        4,
        "Building Team Intelligence"
    )

    teams = conn.execute(
        """
        SELECT team
        FROM team_stats
        """
    ).fetchall()

    total_teams = len(
        teams
    )

    print(
        f"{total_teams:,} teams loaded"
    )

    for idx, row in enumerate(
        teams,
        start=1
    ):

        team = row[0]

        early_goals = 0
        early_concedes = 0

        first_leads = 0
        first_concedes = 0

        comeback_attempts = 0
        successful_comebacks = 0

        lead_games = 0
        retained_leads = 0

        first_half_for = 0
        first_half_against = 0

        second_half_for = 0
        second_half_against = 0

        relevant_matches = [
            m
            for m in matches
            if (
                m[1] == team
                or
                m[2] == team
            )
        ]

        matches_played = len(
            relevant_matches
        )

        for match in relevant_matches:

            match_id = match[0]

            home_team = match[1]
            away_team = match[2]

            final_home = match[3]
            final_away = match[4]

            goals = events_by_match.get(
                match_id,
                []
            )

            if not goals:
                continue

            first_goal_side = None

            running_home = 0
            running_away = 0

            team_led = False

            for goal in goals:

                minute = goal[1]
                side = goal[2]

                if side == 1:
                    running_home += 1

                elif side == 2:
                    running_away += 1

                if first_goal_side is None:
                    first_goal_side = side

                is_team_goal = (
                    (
                        team == home_team
                        and side == 1
                    )
                    or
                    (
                        team == away_team
                        and side == 2
                    )
                )

                if minute <= 30:

                    if is_team_goal:
                        early_goals += 1

                    else:
                        early_concedes += 1

                if minute <= 45:

                    if is_team_goal:
                        first_half_for += 1

                    else:
                        first_half_against += 1

                else:

                    if is_team_goal:
                        second_half_for += 1

                    else:
                        second_half_against += 1

                if team == home_team:

                    if running_home > running_away:
                        team_led = True

                elif team == away_team:

                    if running_away > running_home:
                        team_led = True

            if first_goal_side is not None:

                if (
                    team == home_team
                    and first_goal_side == 1
                ):

                    first_leads += 1

                elif (
                    team == away_team
                    and first_goal_side == 2
                ):

                    first_leads += 1

                else:

                    first_concedes += 1

                    comeback_attempts += 1

                    if team == home_team:

                        if final_home >= final_away:
                            successful_comebacks += 1

                    else:

                        if final_away >= final_home:
                            successful_comebacks += 1

            if team_led:

                lead_games += 1

                if team == home_team:

                    if final_home > final_away:
                        retained_leads += 1

                else:

                    if final_away > final_home:
                        retained_leads += 1

        early_goal_rate = 0
        early_concede_rate = 0

        first_lead_rate = 0
        first_concede_rate = 0

        comeback_rate = 0

        lead_retention_rate = 0

        first_half_goal_diff = 0
        second_half_goal_diff = 0

        burnout_index = 0

        if matches_played > 0:

            early_goal_rate = round(
                (
                    early_goals
                    / matches_played
                )
                * 100,
                2
            )

            early_concede_rate = round(
                (
                    early_concedes
                    / matches_played
                )
                * 100,
                2
            )

            first_lead_rate = round(
                (
                    first_leads
                    / matches_played
                )
                * 100,
                2
            )

            first_concede_rate = round(
                (
                    first_concedes
                    / matches_played
                )
                * 100,
                2
            )

            first_half_goal_diff = round(
                (
                    first_half_for
                    -
                    first_half_against
                )
                / matches_played,
                3
            )

            second_half_goal_diff = round(
                (
                    second_half_for
                    -
                    second_half_against
                )
                / matches_played,
                3
            )

        if comeback_attempts > 0:

            comeback_rate = round(
                (
                    successful_comebacks
                    / comeback_attempts
                )
                * 100,
                2
            )

        if lead_games > 0:

            lead_retention_rate = round(
                (
                    retained_leads
                    / lead_games
                )
                * 100,
                2
            )

        existing = conn.execute(
            """
            SELECT
                two_up_trigger_rate
            FROM team_stats
            WHERE team = ?
            """,
            (
                team,
            )
        ).fetchone()

        trigger_rate = 0

        if (
            existing
            and existing[0] is not None
        ):
            trigger_rate = existing[0]

        burnout_index = round(
            (
                early_goal_rate
                *
                (
                    100
                    -
                    lead_retention_rate
                )
                *
                trigger_rate
            )
            / 10000,
            2
        )

        conn.execute(
            """
            UPDATE team_stats
            SET
                early_goal_rate = ?,
                early_concede_rate = ?,

                first_lead_rate = ?,
                first_concede_rate = ?,

                comeback_rate = ?,

                first_half_goal_diff = ?,
                second_half_goal_diff = ?,

                lead_retention_rate = ?,

                burnout_index = ?

            WHERE team = ?
            """,
            (
                early_goal_rate,
                early_concede_rate,

                first_lead_rate,
                first_concede_rate,

                comeback_rate,

                first_half_goal_diff,
                second_half_goal_diff,

                lead_retention_rate,

                burnout_index,

                team
            )
        )

        if idx % 10 == 0:

            print(
                f"[{idx:,}/{total_teams:,}] "
                f"{team}"
            )

        if (
            idx % 25 == 0
            or idx == total_teams
        ):

            log_progress(
                idx,
                total_teams
            )

    log_step(
        4,
        4,
        "Saving Features"
    )

    conn.commit()
    conn.close()

    elapsed = round(
        time.time()
        - start_time,
        1
    )

    print(
        f"\nTeams Updated: "
        f"{total_teams:,}"
    )

    print(
        f"Runtime: "
        f"{elapsed}s"
    )

    print(
        "\n✅ Complete"
    )


if __name__ == "__main__":
    build_advanced_features()
