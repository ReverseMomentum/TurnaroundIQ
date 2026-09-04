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

from database import get_db, get_odds_movement
from team_normalizer import (
    load_team_stats_names,
    normalize_team,
    resolve_team_stats_name,
)
from training.recency import sample_weight_from_date


STATS_LENGTH = 38

TEAM_STATS_SELECT = """
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

        opponent_turnaround_rate,

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
        abs_retention_delta

     FROM team_stats

     WHERE team = ?
"""


def get_league_turnaround_rate(conn, league):
    row = conn.execute(
        "SELECT turnaround_rate FROM league_stats WHERE league = ?",
        (league,),
    ).fetchone()
    if row:
        return row[0]
    return None


def empty_stats():
    return [None] * STATS_LENGTH


def as_stats(row):
    if not row:
        return empty_stats()
    return [v for v in row]


def safe_sub(left, right):
    if left is None or right is None:
        return None
    return left - right


def resolve_match_date(conn, match_id, processed_at):
    row = conn.execute(
        "SELECT date FROM historical_matches WHERE match_id = ?",
        (str(match_id),),
    ).fetchone()
    if row and row[0]:
        return row[0]
    return processed_at


def ensure_team_row(conn, team, known_teams):
    if team in known_teams:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO team_stats (team, updated_at)
        VALUES (?, datetime('now'))
        """,
        (team,),
    )
    known_teams.append(team)
    print(f"No profile yet: {team} (features NULL)")


def bind_team(conn, raw_name, known_teams):
    resolved, method = resolve_team_stats_name(raw_name, known_teams)
    if resolved:
        if method == "key" and resolved != raw_name:
            print(f"{raw_name} -> {resolved} ({method})")
        return resolved

    name = normalize_team(raw_name) or raw_name
    ensure_team_row(conn, name, known_teams)
    return name


def build_training_data():
    conn = get_db()
    conn.execute("DELETE FROM training_data")

    known_teams = load_team_stats_names()

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
            away_lead_minute,
            processed_at
        FROM match_results
        """
    ).fetchall()

    inserted = 0
    unprofiled = 0

    for match in matches:
        (
            match_id,
            league,
            home_team,
            away_team,
            home_turnaround,
            away_turnaround,
            home_lead_minute,
            away_lead_minute,
            processed_at,
        ) = match

        home_team = bind_team(conn, home_team, known_teams)
        away_team = bind_team(conn, away_team, known_teams)

        home_stats = as_stats(
            conn.execute(TEAM_STATS_SELECT, (home_team,)).fetchone()
        )
        away_stats = as_stats(
            conn.execute(TEAM_STATS_SELECT, (away_team,)).fetchone()
        )

        if all(v is None for v in home_stats):
            unprofiled += 1
        if all(v is None for v in away_stats):
            unprofiled += 1

        league_turnaround_rate = get_league_turnaround_rate(conn, league)
        home_xg_edge = safe_sub(home_stats[0], home_stats[1])
        away_xg_edge = safe_sub(away_stats[0], away_stats[1])

        home_opening_odds, home_odds_movement = get_odds_movement(
            home_team, away_team, home_team
        )
        away_opening_odds, away_odds_movement = get_odds_movement(
            home_team, away_team, away_team
        )

        match_date = resolve_match_date(conn, match_id, processed_at)
        weight = sample_weight_from_date(match_date)

        rows_to_insert = [
            _build_row(
                match_id, league, home_team,
                is_home=1,
                team_stats=home_stats,
                xg_edge=home_xg_edge,
                league_turnaround_rate=league_turnaround_rate,
                opponent_turnaround_rate=away_stats[17],
                lead_minute=home_lead_minute or 0,
                opening_back_odds=home_opening_odds,
                odds_movement=home_odds_movement,
                sample_weight=weight,
                full_turnaround=home_turnaround,
            ),
            _build_row(
                match_id, league, away_team,
                is_home=0,
                team_stats=away_stats,
                xg_edge=away_xg_edge,
                league_turnaround_rate=league_turnaround_rate,
                opponent_turnaround_rate=home_stats[17],
                lead_minute=away_lead_minute or 0,
                opening_back_odds=away_opening_odds,
                odds_movement=away_odds_movement,
                sample_weight=weight,
                full_turnaround=away_turnaround,
            ),
        ]

        for row in rows_to_insert:
            conn.execute(
                """
                INSERT INTO training_data
                (
                    match_id, league, team, is_home,
                    back_odds, lay_odds,
                    avg_xg, avg_xga, xg_edge,
                    goals_last5, conceded_last5,
                    turnaround_pct, two_up_trigger_rate,
                    historical_turnaround_rate, historical_trigger_rate,
                    early_goal_rate, early_concede_rate,
                    first_lead_rate, first_concede_rate,
                    comeback_rate, lead_retention_rate,
                    first_half_goal_diff, second_half_goal_diff,
                    burnout_index,
                    league_turnaround_rate, opponent_turnaround_rate,
                    live_trigger_rate, live_early_goal_rate,
                    live_early_concede_rate, live_first_lead_rate,
                    live_first_concede_rate, live_comeback_rate,
                    live_lead_retention_rate, live_first_half_goal_diff,
                    live_second_half_goal_diff, live_burnout_index,
                    trigger_rate_delta, early_goal_delta,
                    early_concede_delta, first_lead_delta,
                    first_concede_delta, comeback_delta,
                    lead_retention_delta, burnout_delta,
                    abs_trigger_delta, abs_retention_delta,
                    lead_minute, max_lead,
                    opening_back_odds, odds_movement,
                    red_cards_for, red_cards_against,
                    shots_for, shots_against,
                    sample_weight, full_turnaround, created_at
                )
                VALUES (
                    ?,?,?,
                    ?,
                    ?,?,
                    ?,?,
                    ?,
                    ?,?,
                    ?,
                    ?,
                    ?,?,
                    ?,?,
                    ?,?,
                    ?,
                    ?,
                    ?,?,
                    ?,
                    ?,?,
                    ?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,
                    ?,?,
                    ?,?,
                    ?,?,
                    ?,?,
                    ?,?,
                    ?,
                    ?,
                    ?
                )
                """,
                row,
            )

        inserted += 2

    conn.commit()
    conn.close()
    print(f"{inserted} training rows built")
    print(f"{unprofiled} sides had no team_stats profile (NULL features)")


def _build_row(
    match_id, league, team, is_home, team_stats, xg_edge,
    league_turnaround_rate, opponent_turnaround_rate,
    lead_minute, opening_back_odds, odds_movement,
    sample_weight, full_turnaround,
):
    ts = team_stats
    return (
        match_id, league, team, is_home,
        None, None,
        ts[0], ts[1], xg_edge,
        ts[2], ts[3],
        ts[4], ts[5],
        ts[6], ts[7],
        ts[8], ts[9],
        ts[10], ts[11],
        ts[12], ts[13],
        ts[14], ts[15], ts[16],
        league_turnaround_rate, opponent_turnaround_rate,
        ts[18], ts[19], ts[20], ts[21], ts[22], ts[23],
        ts[24], ts[25], ts[26], ts[27],
        ts[28], ts[29], ts[30], ts[31], ts[32], ts[33],
        ts[34], ts[35], ts[36], ts[37],
        lead_minute, 2,
        opening_back_odds, odds_movement,
        None, None, None, None,
        sample_weight, full_turnaround,
        datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    build_training_data()
