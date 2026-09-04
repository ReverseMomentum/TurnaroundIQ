from database import get_db

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

for row in teams:

    team = row[0]

    conn.execute(
        """
        INSERT OR IGNORE INTO team_stats
        (
            team,
            updated_at
        )
        VALUES
        (
            ?,
            datetime('now')
        )
        """,
        (
            team,
        )
    )

conn.commit()
conn.close()
