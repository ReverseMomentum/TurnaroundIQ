"""
One live team_stats pass: trigger rates + last-5 goals from match_results.
Does not touch historical_* columns.
"""

from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db
from team_normalizer import normalize_team

TEAM_STATS_COLUMNS = {
    "avg_xg": "REAL",
    "avg_xga": "REAL",
    "xg_edge": "REAL",
    "goals_last5": "INTEGER",
    "conceded_last5": "INTEGER",
    "matches_played": "INTEGER",
    "two_up_leads": "INTEGER",
    "failed_leads": "INTEGER",
    "turnaround_pct": "REAL",
    "two_up_trigger_rate": "REAL",
    "lead_retention_rate": "REAL",
    "home_turnaround_pct": "REAL",
    "away_turnaround_pct": "REAL",
    "early_goal_rate": "REAL",
    "early_concede_rate": "REAL",
    "first_lead_rate": "REAL",
    "first_concede_rate": "REAL",
    "comeback_rate": "REAL",
    "first_half_goal_diff": "REAL",
    "second_half_goal_diff": "REAL",
    "burnout_index": "REAL",
    "historical_matches": "INTEGER",
    "historical_two_up": "INTEGER",
    "historical_comebacks": "INTEGER",
    "historical_turnaround_rate": "REAL",
    "historical_trigger_rate": "REAL",
    "league_turnaround_rate": "REAL",
    "opponent_turnaround_rate": "REAL",
    "momentum_score": "REAL",
    "attack_rating": "REAL",
    "defence_rating": "REAL",
    "model_weight": "REAL",
    "updated_at": "TEXT",
}


def migrate_team_stats(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS team_stats (team TEXT PRIMARY KEY)")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(team_stats)")}
    for name, typ in TEAM_STATS_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE team_stats ADD COLUMN {name} {typ}")
            print(f"Added team_stats.{name}")
    conn.commit()


def last5_goals(conn, team):
    rows = conn.execute(
        """
        SELECT processed_at, final_home, final_away, 1 AS is_home
        FROM match_results WHERE home_team = ?
        UNION ALL
        SELECT processed_at, final_away, final_home, 0 AS is_home
        FROM match_results WHERE away_team = ?
        ORDER BY processed_at DESC
        LIMIT 5
        """,
        (team, team),
    ).fetchall()
    goals = conceded = 0
    for _when, scored, against, _home in rows:
        goals += scored or 0
        conceded += against or 0
    return goals, conceded


def update_team_stats():
    conn = get_db()
    migrate_team_stats(conn)
    teams = conn.execute(
        """
        SELECT DISTINCT home_team FROM match_results
        UNION
        SELECT DISTINCT away_team FROM match_results
        UNION
        SELECT team FROM team_stats
        """
    ).fetchall()

    rates = {}
    updated = 0
    now = datetime.now(timezone.utc).isoformat()

    for (raw_team,) in teams:
        if not raw_team:
            continue
        team = normalize_team(raw_team)
        home_rows = conn.execute(
            "SELECT home_2up, home_turnaround FROM match_results WHERE home_team = ?",
            (team,),
        ).fetchall()
        away_rows = conn.execute(
            "SELECT away_2up, away_turnaround FROM match_results WHERE away_team = ?",
            (team,),
        ).fetchall()
        matches_played = len(home_rows) + len(away_rows)
        two_up_leads = failed_leads = home_leads = home_fail = away_leads = away_fail = 0
        for trigger, turnaround in home_rows:
            if trigger:
                two_up_leads += 1
                home_leads += 1
                if turnaround:
                    failed_leads += 1
                    home_fail += 1
        for trigger, turnaround in away_rows:
            if trigger:
                two_up_leads += 1
                away_leads += 1
                if turnaround:
                    failed_leads += 1
                    away_fail += 1

        trigger_rate = round(two_up_leads / matches_played * 100, 2) if matches_played else 0
        turnaround_pct = round(failed_leads / two_up_leads * 100, 2) if two_up_leads else 0
        home_pct = round(home_fail / home_leads * 100, 2) if home_leads else 0
        away_pct = round(away_fail / away_leads * 100, 2) if away_leads else 0
        goals_last5, conceded_last5 = last5_goals(conn, team)
        rates[team] = turnaround_pct

        conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
        conn.execute(
            """
            UPDATE team_stats SET
                matches_played = ?,
                two_up_leads = ?,
                failed_leads = ?,
                two_up_trigger_rate = ?,
                turnaround_pct = ?,
                home_turnaround_pct = ?,
                away_turnaround_pct = ?,
                goals_last5 = ?,
                conceded_last5 = ?,
                updated_at = ?
            WHERE team = ?
            """,
            (
                matches_played, two_up_leads, failed_leads,
                trigger_rate, turnaround_pct,
                home_pct, away_pct,
                goals_last5, conceded_last5, now, team,
            ),
        )
        updated += 1

    if rates:
        mean = round(sum(rates.values()) / len(rates), 2)
        for team in rates:
            others = [v for k, v in rates.items() if k != team]
            opp = round(sum(others) / len(others), 2) if others else mean
            conn.execute(
                "UPDATE team_stats SET opponent_turnaround_rate = ? WHERE team = ?",
                (opp, team),
            )

    conn.commit()
    conn.close()
    print(f"{updated} live team_stats rows updated")


if __name__ == "__main__":
    update_team_stats()
