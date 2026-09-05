"""
Replay historical_events into team_stats.
Merges build_historical_team_intelligence + build_historical_advanced_features.
"""

from collections import defaultdict
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db, save_league_stats
from team_normalizer import normalize_team


def build():
    conn = get_db()
    matches = conn.execute(
        """
        SELECT match_id, home_team, away_team, final_home, final_away, league
        FROM historical_matches
        """
    ).fetchall()
    events = conn.execute(
        """
        SELECT match_id, minute, side, is_goal
        FROM historical_events
        WHERE is_goal = 1
        ORDER BY match_id, minute
        """
    ).fetchall()
    events_by_match = defaultdict(list)
    for event in events:
        events_by_match[event[0]].append(event)

    teams = sorted({
        normalize_team(row[1]) for row in matches
    } | {
        normalize_team(row[2]) for row in matches
    })
    print(f"{len(matches)} matches, {len(events)} goals, {len(teams)} teams")

    league_acc = defaultdict(lambda: {"matches": 0, "two_up": 0, "comeback": 0})

    for team in teams:
        two_up_count = comeback_count = 0
        early_goals = early_concedes = 0
        first_leads = first_concedes = 0
        comeback_attempts = successful_comebacks = 0
        lead_games = retained_leads = 0
        first_half_for = first_half_against = 0
        second_half_for = second_half_against = 0
        match_count = 0

        for match_id, home, away, final_home, final_away, league in matches:
            home = normalize_team(home)
            away = normalize_team(away)
            if team not in {home, away}:
                continue
            match_count += 1
            goals = events_by_match.get(match_id, [])
            home_score = away_score = 0
            team_went_two_up = False
            first_goal_side = None
            team_led = False
            for _mid, minute, side, is_goal in goals:
                if not is_goal:
                    continue
                if side == 1:
                    home_score += 1
                elif side == 2:
                    away_score += 1
                if first_goal_side is None:
                    first_goal_side = side
                is_team_goal = (team == home and side == 1) or (team == away and side == 2)
                minute = minute or 0
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
                if team == home and home_score - away_score >= 2:
                    team_went_two_up = True
                if team == away and away_score - home_score >= 2:
                    team_went_two_up = True
                if team == home and home_score > away_score:
                    team_led = True
                if team == away and away_score > home_score:
                    team_led = True

            if team_went_two_up:
                two_up_count += 1
                dropped = (
                    (team == home and (final_home or 0) <= (final_away or 0))
                    or (team == away and (final_away or 0) <= (final_home or 0))
                )
                if dropped:
                    comeback_count += 1
                if league:
                    league_acc[league]["two_up"] += 1
                    if dropped:
                        league_acc[league]["comeback"] += 1
            if league:
                league_acc[league]["matches"] += 1

            if first_goal_side is not None:
                scored_first = (team == home and first_goal_side == 1) or (
                    team == away and first_goal_side == 2
                )
                if scored_first:
                    first_leads += 1
                else:
                    first_concedes += 1
                    comeback_attempts += 1
                    if team == home and (final_home or 0) >= (final_away or 0):
                        successful_comebacks += 1
                    if team == away and (final_away or 0) >= (final_home or 0):
                        successful_comebacks += 1
            if team_led:
                lead_games += 1
                if team == home and (final_home or 0) > (final_away or 0):
                    retained_leads += 1
                if team == away and (final_away or 0) > (final_home or 0):
                    retained_leads += 1

        turnaround_rate = round(comeback_count / two_up_count * 100, 2) if two_up_count else 0
        trigger_rate = round(two_up_count / match_count * 100, 2) if match_count else 0
        early_goal_rate = round(early_goals / match_count * 100, 2) if match_count else 0
        early_concede_rate = round(early_concedes / match_count * 100, 2) if match_count else 0
        first_lead_rate = round(first_leads / match_count * 100, 2) if match_count else 0
        first_concede_rate = round(first_concedes / match_count * 100, 2) if match_count else 0
        comeback_rate = (
            round(successful_comebacks / comeback_attempts * 100, 2) if comeback_attempts else 0
        )
        lead_retention_rate = (
            round(retained_leads / lead_games * 100, 2) if lead_games else 0
        )
        first_half_goal_diff = (
            round((first_half_for - first_half_against) / match_count, 3) if match_count else 0
        )
        second_half_goal_diff = (
            round((second_half_for - second_half_against) / match_count, 3) if match_count else 0
        )
        burnout_index = round(
            early_goal_rate * (100 - lead_retention_rate) * trigger_rate / 10000, 2
        )

        conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
        conn.execute(
            """
            UPDATE team_stats SET
                historical_matches = ?,
                historical_two_up = ?,
                historical_comebacks = ?,
                historical_turnaround_rate = ?,
                historical_trigger_rate = ?,
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
                match_count, two_up_count, comeback_count,
                turnaround_rate, trigger_rate,
                early_goal_rate, early_concede_rate,
                first_lead_rate, first_concede_rate,
                comeback_rate, first_half_goal_diff, second_half_goal_diff,
                lead_retention_rate, burnout_index, team,
            ),
        )

    conn.commit()

    for league, acc in league_acc.items():
        trigger = round(acc["two_up"] / acc["matches"] * 100, 2) if acc["matches"] else 0
        turn = round(acc["comeback"] / acc["two_up"] * 100, 2) if acc["two_up"] else 0
        save_league_stats(league, acc["matches"], acc["two_up"], acc["comeback"], trigger, turn)

    conn.close()
    print(f"{len(teams)} historical profiles built")


if __name__ == "__main__":
    build()
