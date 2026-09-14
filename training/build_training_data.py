"""
Build training_data from:
  1) live match_results (all sides)
  2) historical_matches + historical_events (sides that went 2-up only)

Historical full_turnaround matches results_collector:
  went 2-up AND finished level or behind.
"""
from collections import defaultdict
from datetime import datetime, timezone
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db, get_odds_movement
from team_normalizer import load_team_stats_names, normalize_team, resolve_team_stats_name
from training.recency import sample_weight_from_date

STATS_LENGTH = 38

TRAINING_COLUMNS = {
    "match_id": "TEXT",
    "league": "TEXT",
    "team": "TEXT",
    "is_home": "INTEGER",
    "back_odds": "REAL",
    "lay_odds": "REAL",
    "avg_xg": "REAL",
    "avg_xga": "REAL",
    "xg_edge": "REAL",
    "goals_last5": "INTEGER",
    "conceded_last5": "INTEGER",
    "turnaround_pct": "REAL",
    "two_up_trigger_rate": "REAL",
    "historical_turnaround_rate": "REAL",
    "historical_trigger_rate": "REAL",
    "early_goal_rate": "REAL",
    "early_concede_rate": "REAL",
    "first_lead_rate": "REAL",
    "first_concede_rate": "REAL",
    "comeback_rate": "REAL",
    "lead_retention_rate": "REAL",
    "first_half_goal_diff": "REAL",
    "second_half_goal_diff": "REAL",
    "burnout_index": "REAL",
    "league_turnaround_rate": "REAL",
    "opponent_turnaround_rate": "REAL",
    "live_trigger_rate": "REAL",
    "live_early_goal_rate": "REAL",
    "live_early_concede_rate": "REAL",
    "live_first_lead_rate": "REAL",
    "live_first_concede_rate": "REAL",
    "live_comeback_rate": "REAL",
    "live_lead_retention_rate": "REAL",
    "live_first_half_goal_diff": "REAL",
    "live_second_half_goal_diff": "REAL",
    "live_burnout_index": "REAL",
    "trigger_rate_delta": "REAL",
    "early_goal_delta": "REAL",
    "early_concede_delta": "REAL",
    "first_lead_delta": "REAL",
    "first_concede_delta": "REAL",
    "comeback_delta": "REAL",
    "lead_retention_delta": "REAL",
    "burnout_delta": "REAL",
    "abs_trigger_delta": "REAL",
    "abs_retention_delta": "REAL",
    "lead_minute": "INTEGER",
    "max_lead": "INTEGER",
    "opening_back_odds": "REAL",
    "odds_movement": "REAL",
    "red_cards_for": "INTEGER",
    "red_cards_against": "INTEGER",
    "shots_for": "INTEGER",
    "shots_against": "INTEGER",
    "sample_weight": "REAL",
    "full_turnaround": "INTEGER",
    "created_at": "TEXT",
}

TEAM_STATS_SELECT = """
    SELECT
        avg_xg, avg_xga, goals_last5, conceded_last5,
        turnaround_pct, two_up_trigger_rate,
        historical_turnaround_rate, historical_trigger_rate,
        early_goal_rate, early_concede_rate,
        first_lead_rate, first_concede_rate,
        comeback_rate, lead_retention_rate,
        first_half_goal_diff, second_half_goal_diff,
        burnout_index, opponent_turnaround_rate,
        live_trigger_rate, live_early_goal_rate,
        live_early_concede_rate, live_first_lead_rate,
        live_first_concede_rate, live_comeback_rate,
        live_lead_retention_rate, live_first_half_goal_diff,
        live_second_half_goal_diff, live_burnout_index,
        trigger_rate_delta, early_goal_delta, early_concede_delta,
        first_lead_delta, first_concede_delta, comeback_delta,
        lead_retention_delta, burnout_delta,
        abs_trigger_delta, abs_retention_delta
    FROM team_stats WHERE team = ?
"""

INSERT_SQL = """
    INSERT INTO training_data (
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
    ) VALUES (
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?
    )
"""


def migrate_training_data(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS training_data (id INTEGER PRIMARY KEY AUTOINCREMENT)"
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(training_data)")}
    for name, typ in TRAINING_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE training_data ADD COLUMN {name} {typ}")
            print(f"Added training_data.{name}")
    conn.commit()


def get_league_turnaround_rate(conn, league):
    try:
        row = conn.execute(
            "SELECT turnaround_rate FROM league_stats WHERE league = ?",
            (league,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
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
    try:
        row = conn.execute(
            "SELECT date FROM historical_matches WHERE match_id = ?",
            (str(match_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        return processed_at
    if row and row[0]:
        return row[0]
    return processed_at


def ensure_team_row(conn, team, known_teams):
    if team in known_teams:
        return
    conn.execute(
        "INSERT OR IGNORE INTO team_stats (team, updated_at) VALUES (?, datetime('now'))",
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
        ts[2], ts[3], ts[4], ts[5], ts[6], ts[7],
        ts[8], ts[9], ts[10], ts[11], ts[12], ts[13],
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


def analyze_historical_goals(goals):
    """Replay goal events. side 1 = home, 2 = away."""
    home_score = away_score = 0
    home_2up = away_2up = False
    home_lead_minute = away_lead_minute = 0
    for minute, side, is_goal in goals:
        if not is_goal:
            continue
        minute = int(minute or 0)
        if side == 1:
            home_score += 1
        elif side == 2:
            away_score += 1
        else:
            continue
        if home_score - away_score >= 2:
            home_2up = True
            if home_lead_minute == 0:
                home_lead_minute = minute
        if away_score - home_score >= 2:
            away_2up = True
            if away_lead_minute == 0:
                away_lead_minute = minute
    return {
        "home_score": home_score,
        "away_score": away_score,
        "home_2up": home_2up,
        "away_2up": away_2up,
        "home_lead_minute": home_lead_minute,
        "away_lead_minute": away_lead_minute,
    }


def insert_side(
    conn, known_teams, match_id, league, team, is_home,
    opponent_stats, league_turnaround_rate, lead_minute,
    match_date, full_turnaround,
):
    team = bind_team(conn, team, known_teams)
    stats = as_stats(conn.execute(TEAM_STATS_SELECT, (team,)).fetchone())
    unprofiled = 1 if all(v is None for v in stats) else 0
    xg_edge = safe_sub(stats[0], stats[1])
    opening_odds, odds_movement = get_odds_movement(
        team if is_home else None,
        None if is_home else team,
        team,
    )
    # get_odds_movement expects home, away, selection — use match teams when possible
    weight = sample_weight_from_date(match_date)
    row = _build_row(
        match_id, league, team, is_home, stats, xg_edge,
        league_turnaround_rate, opponent_stats[17] if opponent_stats else None,
        lead_minute or 0, opening_odds, odds_movement,
        weight, int(full_turnaround),
    )
    conn.execute(INSERT_SQL, row)
    return unprofiled


def insert_side_with_odds(
    conn, known_teams, match_id, league, home_team, away_team,
    team, is_home, opp_stats, league_rate, lead_minute, match_date, full_turnaround,
):
    team = bind_team(conn, team, known_teams)
    stats = as_stats(conn.execute(TEAM_STATS_SELECT, (team,)).fetchone())
    unprofiled = 1 if all(v is None for v in stats) else 0
    xg_edge = safe_sub(stats[0], stats[1])
    opening_odds, odds_movement = get_odds_movement(home_team, away_team, team)
    weight = sample_weight_from_date(match_date)
    row = _build_row(
        match_id, league, team, is_home, stats, xg_edge,
        league_rate, opp_stats[17] if opp_stats else None,
        lead_minute or 0, opening_odds, odds_movement,
        weight, int(full_turnaround),
    )
    conn.execute(INSERT_SQL, row)
    return unprofiled


def add_live_rows(conn, known_teams):
    matches = conn.execute(
        """
        SELECT match_id, league, home_team, away_team,
               home_turnaround, away_turnaround,
               home_lead_minute, away_lead_minute, processed_at
        FROM match_results
        """
    ).fetchall()
    inserted = 0
    unprofiled = 0
    for match in matches:
        (
            match_id, league, home_team, away_team,
            home_turnaround, away_turnaround,
            home_lead_minute, away_lead_minute, processed_at,
        ) = match
        home_team = bind_team(conn, home_team, known_teams)
        away_team = bind_team(conn, away_team, known_teams)
        home_stats = as_stats(conn.execute(TEAM_STATS_SELECT, (home_team,)).fetchone())
        away_stats = as_stats(conn.execute(TEAM_STATS_SELECT, (away_team,)).fetchone())
        if all(v is None for v in home_stats):
            unprofiled += 1
        if all(v is None for v in away_stats):
            unprofiled += 1
        league_rate = get_league_turnaround_rate(conn, league)
        match_date = resolve_match_date(conn, match_id, processed_at)
        for team, is_home, stats, opp, lead, label in (
            (home_team, 1, home_stats, away_stats, home_lead_minute, home_turnaround),
            (away_team, 0, away_stats, home_stats, away_lead_minute, away_turnaround),
        ):
            opening_odds, odds_movement = get_odds_movement(home_team, away_team, team)
            weight = sample_weight_from_date(match_date)
            xg_edge = safe_sub(stats[0], stats[1])
            row = _build_row(
                match_id, league, team, is_home, stats, xg_edge,
                league_rate, opp[17],
                lead or 0, opening_odds, odds_movement,
                weight, label,
            )
            conn.execute(INSERT_SQL, row)
            inserted += 1
    print(f"{inserted} live training rows")
    return inserted, unprofiled


def add_historical_rows(conn, known_teams):
    """One row per side that went 2-up in historical_events."""
    try:
        matches = conn.execute(
            """
            SELECT match_id, league, home_team, away_team,
                   final_home, final_away, date
            FROM historical_matches
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"historical_matches missing: {exc}")
        return 0, 0

    try:
        events = conn.execute(
            """
            SELECT match_id, minute, side, is_goal
            FROM historical_events
            WHERE is_goal = 1
            ORDER BY match_id, minute
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"historical_events missing: {exc}")
        return 0, 0

    events_by_match = defaultdict(list)
    for match_id, minute, side, is_goal in events:
        events_by_match[match_id].append((minute, side, is_goal))

    inserted = 0
    unprofiled = 0
    two_up_sides = 0
    skipped_no_events = 0

    for match_id, league, home, away, final_home, final_away, date in matches:
        goals = events_by_match.get(match_id)
        if not goals:
            skipped_no_events += 1
            continue
        analysis = analyze_historical_goals(goals)
        # Prefer event tally; fall back to stored finals for turnaround check
        fh = analysis["home_score"] if analysis["home_score"] or analysis["away_score"] else (final_home or 0)
        fa = analysis["away_score"] if analysis["home_score"] or analysis["away_score"] else (final_away or 0)
        if final_home is not None:
            fh = final_home
        if final_away is not None:
            fa = final_away

        home_team = bind_team(conn, home, known_teams)
        away_team = bind_team(conn, away, known_teams)
        home_stats = as_stats(conn.execute(TEAM_STATS_SELECT, (home_team,)).fetchone())
        away_stats = as_stats(conn.execute(TEAM_STATS_SELECT, (away_team,)).fetchone())
        league_rate = get_league_turnaround_rate(conn, league)
        match_date = date or ""

        if analysis["home_2up"]:
            two_up_sides += 1
            label = int(fh <= fa)
            if all(v is None for v in home_stats):
                unprofiled += 1
            opening_odds, odds_movement = get_odds_movement(home_team, away_team, home_team)
            weight = sample_weight_from_date(match_date)
            xg_edge = safe_sub(home_stats[0], home_stats[1])
            row = _build_row(
                match_id, league, home_team, 1, home_stats, xg_edge,
                league_rate, away_stats[17],
                analysis["home_lead_minute"], opening_odds, odds_movement,
                weight, label,
            )
            conn.execute(INSERT_SQL, row)
            inserted += 1

        if analysis["away_2up"]:
            two_up_sides += 1
            label = int(fa <= fh)
            if all(v is None for v in away_stats):
                unprofiled += 1
            opening_odds, odds_movement = get_odds_movement(home_team, away_team, away_team)
            weight = sample_weight_from_date(match_date)
            xg_edge = safe_sub(away_stats[0], away_stats[1])
            row = _build_row(
                match_id, league, away_team, 0, away_stats, xg_edge,
                league_rate, home_stats[17],
                analysis["away_lead_minute"], opening_odds, odds_movement,
                weight, label,
            )
            conn.execute(INSERT_SQL, row)
            inserted += 1

    print(f"{inserted} historical 2-up training rows ({two_up_sides} two-up sides)")
    print(f"{skipped_no_events} historical matches had no goal events")
    return inserted, unprofiled


def build_training_data():
    conn = get_db()
    migrate_training_data(conn)
    conn.execute("DELETE FROM training_data")
    known_teams = load_team_stats_names()

    live_n, live_un = add_live_rows(conn, known_teams)
    hist_n, hist_un = add_historical_rows(conn, known_teams)

    conn.commit()
    conn.close()
    total = live_n + hist_n
    print(f"{total} training rows built (live {live_n} + historical {hist_n})")
    print(f"{live_un + hist_un} sides had no team_stats profile (NULL features)")


if __name__ == "__main__":
    build_training_data()
