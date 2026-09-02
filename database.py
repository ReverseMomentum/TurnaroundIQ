import sqlite3
from datetime import (
    datetime,
    timezone
)

DB_NAME = "two_up.db"


def get_db():
    return sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )


def create_tables():

    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS tracked_bets (

    id TEXT PRIMARY KEY,

    match_name TEXT,
    team TEXT,
    league TEXT,
    kickoff TEXT,

    bookmaker TEXT,

    back_odds REAL,
    lay_odds REAL,

    estimated_lay INTEGER,

    stake REAL,
    commission REAL,

    lay_stake REAL,
    liability REAL,

    qualifying_loss REAL,
    outcome_fta REAL,

    fta_pct REAL,
    ev_pct REAL,

    expected_profit REAL,
    actual_profit REAL,

    actual_fta INTEGER,

    status TEXT,
    result TEXT,

    model_version TEXT,

    created_at TEXT,
    settled_at TEXT

)
""")


    conn.execute("""
    CREATE TABLE IF NOT EXISTS team_aliases (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        alias TEXT UNIQUE,

        canonical_name TEXT,

        source TEXT,

        created_at TEXT

    )
    """)


    conn.execute("""
    CREATE TABLE IF NOT EXISTS fixture_cache (

        fixture_id TEXT PRIMARY KEY,

        last_checked TEXT,

        kickoff TEXT

    )
    """)


    conn.execute("""
    CREATE TABLE IF NOT EXISTS odds_history (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        timestamp TEXT,

        match_id TEXT,
        kickoff TEXT,
        league TEXT,

        home_team TEXT,
        away_team TEXT,

        selection TEXT,

        bookmaker TEXT,
        exchange_name TEXT,

        back_odds REAL,
        lay_odds REAL

    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS match_results (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        match_id TEXT,

        league TEXT,

        home_team TEXT,
        away_team TEXT,

        final_home INTEGER,
        final_away INTEGER,

        home_2up INTEGER,
        away_2up INTEGER,

        home_turnaround INTEGER,
        away_turnaround INTEGER,

        home_lead_minute INTEGER,
        away_lead_minute INTEGER,

        processed_at TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS historical_matches (

        match_id TEXT PRIMARY KEY,

        date TEXT,

        league TEXT,
        season TEXT,

        country TEXT,

        home_team TEXT,
        away_team TEXT,

        final_home INTEGER,
        final_away INTEGER,

        odd_h REAL,
        odd_d REAL,
        odd_a REAL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS historical_events (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        match_id TEXT,

        minute INTEGER,

        event_type INTEGER,
        event_type2 INTEGER,

        side INTEGER,

        team TEXT,

        player TEXT,

        is_goal INTEGER,

        situation INTEGER
    )
    """)
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS team_stats (

        team TEXT PRIMARY KEY,

        avg_xg REAL,
        avg_xga REAL,

        xg_edge REAL,

        goals_last5 INTEGER,
        conceded_last5 INTEGER,

        turnaround_pct REAL,

        two_up_leads INTEGER,
        failed_leads INTEGER,

        home_turnaround_pct REAL,
        away_turnaround_pct REAL,

        historical_matches INTEGER,
        historical_two_up INTEGER,
        historical_comebacks INTEGER,

        two_up_trigger_rate REAL,
        historical_turnaround_rate REAL,

        league_turnaround_rate REAL,
        opponent_turnaround_rate REAL,

        matches_played INTEGER,

        lead_retention_rate REAL,

        recent_turnaround_rate REAL,

        early_goal_rate REAL,

        first_half_goal_diff REAL,

        second_half_goal_diff REAL,

        burnout_index REAL,


        updated_at TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS training_data (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        match_id TEXT,

        league TEXT,
        team TEXT,

        is_home INTEGER,

        back_odds REAL,
        lay_odds REAL,

        avg_xg REAL,
        avg_xga REAL,

        xg_edge REAL,

        goals_last5 INTEGER,
        conceded_last5 INTEGER,

        turnaround_pct REAL,

        two_up_trigger_rate REAL,

        historical_turnaround_rate REAL,

        league_turnaround_rate REAL,
        opponent_turnaround_rate REAL,

        lead_minute INTEGER,
        max_lead INTEGER,

        opening_back_odds REAL,
        odds_movement REAL,

        red_cards_for INTEGER,
        red_cards_against INTEGER,

        shots_for INTEGER,
        shots_against INTEGER,

        sample_weight REAL,

        full_turnaround INTEGER,

        created_at TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS settings (

        setting_name TEXT PRIMARY KEY,
        setting_value TEXT

    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS processed_fixtures (

        fixture_id TEXT PRIMARY KEY,
        processed_at TEXT

    )
    """)

    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS model_runs (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        model_name TEXT,

        version TEXT,

        trained_at TEXT,

        training_rows INTEGER,

        brier_score REAL,

        log_loss REAL,

        roc_auc REAL,

        notes TEXT

    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS league_stats (

        league TEXT PRIMARY KEY,

        matches INTEGER,

        two_up_count INTEGER,

        comeback_count INTEGER,

        trigger_rate REAL,

        turnaround_rate REAL,

        updated_at TEXT

    )
    """)

    conn.commit()
    conn.close()


def save_setting(
    name,
    value
):

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO settings
        (
            setting_name,
            setting_value
        )
        VALUES
        (?, ?)
        """,
        (
            name,
            str(value)
        )
    )

    conn.commit()
    conn.close()


def get_setting(
    name,
    default_value=None
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT setting_value
        FROM settings
        WHERE setting_name = ?
        """,
        (name,)
    ).fetchone()

    conn.close()

    if row:
        return row[0]

    return default_value


def save_tracked_bet(
    data
):

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO tracked_bets
        VALUES
        (
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?
        )
        """,
        (
            data["id"],

            data["match_name"],
            data["team"],
            data["league"],
            data["kickoff"],

            data["bookmaker"],

            data["back_odds"],
            data["lay_odds"],

            data["estimated_lay"],

            data["stake"],
            data["commission"],

            data["lay_stake"],
            data["liability"],

            data["qualifying_loss"],
            data["outcome_fta"],

            data["fta_pct"],
            data["ev_pct"],

            data["expected_profit"],
            data["actual_profit"],

            data["actual_fta"],

            data["status"],
            data["result"],


            data["model_version"],

            data["created_at"],
            data["settled_at"]
        )
    )

    conn.commit()
    conn.close()



def get_tracked_bets():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM tracked_bets
        ORDER BY created_at DESC
        """
    ).fetchall()

    conn.close()

    return rows


def delete_tracked_bet(
    bet_id
):

    conn = get_db()

    conn.execute(
        """
        DELETE FROM tracked_bets
        WHERE id = ?
        """,
        (bet_id,)
    )

    conn.commit()
    conn.close()


def update_bet_result(
    bet_id,
    result,
    actual_profit,
    status="Settled"
):

    conn = get_db()

    conn.execute(
        """
        UPDATE tracked_bets
        SET
            result = ?,
            actual_profit = ?,
            status = ?,
            settled_at = datetime('now')
        WHERE id = ?
        """,
        (
            result,
            actual_profit,
            status,
            bet_id
        )
    )

    conn.commit()
    conn.close()


def get_performance_stats():

    conn = get_db()

    stats = conn.execute(
        """
        SELECT

            COUNT(*),

            COALESCE(
                SUM(expected_profit),
                0
            ),

            COALESCE(
                SUM(actual_profit),
                0
            )

        FROM tracked_bets
        """
    ).fetchone()

    conn.close()

    return stats


def save_model_run(
    model_name,
    version,
    training_rows,
    brier_score,
    log_loss,
    roc_auc,
    notes=""
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO model_runs
        (
            model_name,
            version,
            trained_at,
            training_rows,
            brier_score,
            log_loss,
            roc_auc,
            notes
        )

        VALUES
        (
            ?,
            ?,
            datetime('now'),
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            model_name,
            version,
            training_rows,
            brier_score,
            log_loss,
            roc_auc,
            notes
        )
    )

    conn.commit()
    conn.close()


def get_model_runs():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM model_runs
        ORDER BY trained_at DESC
        """
    ).fetchall()

    conn.close()

    return rows


def get_tracked_teams():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT team
        FROM team_stats
        """
    ).fetchall()

    conn.close()

    return {
        row[0]
        for row in rows
    }


def save_league_stats(
    league,
    matches,
    two_up_count,
    comeback_count,
    trigger_rate,
    turnaround_rate
):

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO league_stats
        (
            league,
            matches,
            two_up_count,
            comeback_count,
            trigger_rate,
            turnaround_rate,
            updated_at
        )
        VALUES
        (
            ?, ?, ?, ?, ?, ?,
            datetime('now')
        )
        """,
        (
            league,
            matches,
            two_up_count,
            comeback_count,
            trigger_rate,
            turnaround_rate
        )
    )

    conn.commit()
    conn.close()


def get_league_stats():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM league_stats
        """
    ).fetchall()

    conn.close()

    return rows


def save_team_alias(
    alias,
    canonical_name,
    source="manual"
):
    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO team_aliases
        (
            alias,
            canonical_name,
            source,
            created_at
        )
        VALUES
        (
            ?, ?, ?,
            datetime('now')
        )
        """,
        (
            alias,
            canonical_name,
            source
        )
    )

    conn.commit()
    conn.close()

def get_team_alias(
    alias
):
    conn = get_db()

    row = conn.execute(
        """
        SELECT canonical_name
        FROM team_aliases
        WHERE LOWER(alias) = ?
        """,
        (
            alias.lower(),
        )
    ).fetchone()

    conn.close()

    if row:
        return row[0]

    return None

def get_all_team_aliases():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            alias,
            canonical_name,
            source
        FROM team_aliases
        ORDER BY canonical_name
        """
    ).fetchall()

    conn.close()

    return rows

def delete_team_alias(
    alias
):
    conn = get_db()

    conn.execute(
        """
        DELETE FROM team_aliases
        WHERE alias = ?
        """,
        (alias,)
    )

    conn.commit()
    conn.close()

def save_odds_history(
    match_id,
    kickoff,
    league,
    home_team,
    away_team,
    selection,
    bookmaker,
    back_odds,
    lay_odds=None,
    exchange_name=None
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO odds_history
        (
            timestamp,

            match_id,
            kickoff,

            league,

            home_team,
            away_team,

            selection,

            bookmaker,
            exchange_name,

            back_odds,
            lay_odds
        )

        VALUES
        (
            datetime('now'),

            ?, ?, ?,

            ?, ?,

            ?,

            ?, ?,

            ?, ?
        )
        """,
        (
            match_id,
            kickoff,
            league,

            home_team,
            away_team,

            selection,

            bookmaker,
            exchange_name,

            back_odds,
            lay_odds
        )
    )

    conn.commit()
    conn.close()


def get_latest_odds():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT

            match_id,
            kickoff,
            league,

            home_team,
            away_team,

            selection,

            bookmaker,

            back_odds

        FROM odds_history

        ORDER BY kickoff ASC
        """
    ).fetchall()

    conn.close()

    return rows



def get_pending_bets():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM tracked_bets
        WHERE status = 'Pending'
        ORDER BY kickoff ASC
        """
    ).fetchall()

    conn.close()

    return rows


def get_match_result(
    home_team,
    away_team
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT
            home_2up,
            away_2up,
            home_turnaround,
            away_turnaround
        FROM match_results
        WHERE home_team = ?
        AND away_team = ?
        ORDER BY processed_at DESC
        LIMIT 1
        """,
        (
            home_team,
            away_team
        )
    ).fetchone()

    conn.close()

    return row

def fixture_recently_checked(
    fixture_id,
    minutes=30
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT last_checked
        FROM fixture_cache
        WHERE fixture_id = ?
        """,
        (
            fixture_id,
        )
    ).fetchone()

    conn.close()

    if not row:
        return False

    from datetime import (
        datetime,
        timezone
    )

    last_checked = (
        datetime.fromisoformat(
            row[0]
        )
    )

    age = (
        datetime.now(
            timezone.utc
        )
        -
        last_checked
    )

    return (
        age.total_seconds()
        <
        (
            minutes * 60
        )
    )


def update_fixture_cache(
    fixture_id,
    kickoff
):

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO
        fixture_cache
        (
            fixture_id,
            kickoff,
            last_checked
        )
        VALUES
        (
            ?,
            ?,
            datetime('now')
        )
        """,
        (
            fixture_id,
            kickoff
        )
    )

    conn.commit()
    conn.close()



def update_bet_fta(
    bet_id,
    actual_fta
):

    conn = get_db()

    conn.execute(
        """
        UPDATE tracked_bets
        SET actual_fta = ?
        WHERE id = ?
        """,
        (
            actual_fta,
            bet_id
        )
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":

    create_tables()

    print(
        "Database ready"
    )
