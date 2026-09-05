"""
One live team_stats pass: trigger rates + home/away turnaround + opponent rate.
Replaces update_team_profiles.py + update_turnaround_stats.py.
"""

from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db
from team_normalizer import normalize_team


def update_team_stats():
    conn = get_db()
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
        retention = round((two_up_leads - failed_leads) / two_up_leads * 100, 2) if two_up_leads else 100
        home_pct = round(home_fail / home_leads * 100, 2) if home_leads else 0
        away_pct = round(away_fail / away_leads * 100, 2) if away_leads else 0
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
                lead_retention_rate = ?,
                home_turnaround_pct = ?,
                away_turnaround_pct = ?,
                updated_at = ?
            WHERE team = ?
            """,
            (
                matches_played, two_up_leads, failed_leads,
                trigger_rate, turnaround_pct, retention,
                home_pct, away_pct, now, team,
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
