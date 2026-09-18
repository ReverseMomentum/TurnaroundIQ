"""
User-entered opportunities / bets — no odds_history required.

Allows paper-tracking FTA results from the app.
"""

from datetime import datetime, timezone
import json

from database import get_db


def ensure_tracked_tables():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_user_id TEXT NOT NULL,
            match_id TEXT,
            league TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            team TEXT NOT NULL,
            is_home INTEGER DEFAULT 1,
            kickoff TEXT,
            bookmaker TEXT,
            back_odds REAL,
            lay_odds REAL,
            stake REAL,
            commission REAL DEFAULT 2.0,
            lay_stake REAL,
            liability REAL,
            fta_pct REAL,
            notes TEXT,
            status TEXT DEFAULT 'open',
            result TEXT,
            actual_profit REAL,
            actual_fta INTEGER,
            created_at TEXT,
            settled_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _row_to_dict(row):
    keys = [
        "id", "app_user_id", "match_id", "league", "home_team", "away_team",
        "team", "is_home", "kickoff", "bookmaker", "back_odds", "lay_odds",
        "stake", "commission", "lay_stake", "liability", "fta_pct", "notes",
        "status", "result", "actual_profit", "actual_fta", "created_at", "settled_at",
    ]
    d = dict(zip(keys, row))
    d["match"] = f"{d['home_team']} vs {d['away_team']}"
    d["estimated_lay"] = d.get("lay_odds") is None
    d["source"] = "manual"
    return d


def list_tracked(app_user_id, status=None, limit=50):
    ensure_tracked_tables()
    conn = get_db()
    if status:
        rows = conn.execute(
            """
            SELECT id, app_user_id, match_id, league, home_team, away_team,
                   team, is_home, kickoff, bookmaker, back_odds, lay_odds,
                   stake, commission, lay_stake, liability, fta_pct, notes,
                   status, result, actual_profit, actual_fta, created_at, settled_at
            FROM tracked_bets
            WHERE app_user_id = ? AND status = ?
            ORDER BY id DESC LIMIT ?
            """,
            (app_user_id, status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, app_user_id, match_id, league, home_team, away_team,
                   team, is_home, kickoff, bookmaker, back_odds, lay_odds,
                   stake, commission, lay_stake, liability, fta_pct, notes,
                   status, result, actual_profit, actual_fta, created_at, settled_at
            FROM tracked_bets
            WHERE app_user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (app_user_id, limit),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def create_tracked(app_user_id, data):
    ensure_tracked_tables()
    now = datetime.now(timezone.utc).isoformat()
    home = (data.get("home_team") or "").strip()
    away = (data.get("away_team") or "").strip()
    team = (data.get("team") or home).strip()
    if not home or not away:
        raise ValueError("home_team and away_team required")

    is_home = 1 if data.get("is_home", team == home) else 0
    back = data.get("back_odds")
    lay = data.get("lay_odds")
    stake = data.get("stake") if data.get("stake") is not None else 40.0
    commission = data.get("commission") if data.get("commission") is not None else 2.0

    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO tracked_bets (
            app_user_id, match_id, league, home_team, away_team, team, is_home,
            kickoff, bookmaker, back_odds, lay_odds, stake, commission,
            lay_stake, liability, fta_pct, notes, status, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            app_user_id,
            data.get("match_id"),
            data.get("league") or "",
            home,
            away,
            team,
            is_home,
            data.get("kickoff"),
            data.get("bookmaker") or "Manual",
            back,
            lay,
            stake,
            commission,
            data.get("lay_stake"),
            data.get("liability"),
            data.get("fta_pct"),
            data.get("notes"),
            "open",
            now,
        ),
    )
    bet_id = cur.lastrowid
    conn.commit()
    row = conn.execute(
        """
        SELECT id, app_user_id, match_id, league, home_team, away_team,
               team, is_home, kickoff, bookmaker, back_odds, lay_odds,
               stake, commission, lay_stake, liability, fta_pct, notes,
               status, result, actual_profit, actual_fta, created_at, settled_at
        FROM tracked_bets WHERE id = ?
        """,
        (bet_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def settle_tracked(app_user_id, bet_id, result, actual_profit=None, actual_fta=None):
    """
    result: won | lost | void | fta | no_fta
    """
    ensure_tracked_tables()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM tracked_bets WHERE id = ? AND app_user_id = ?",
        (bet_id, app_user_id),
    ).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute(
        """
        UPDATE tracked_bets SET
            status = 'settled',
            result = ?,
            actual_profit = ?,
            actual_fta = ?,
            settled_at = ?
        WHERE id = ? AND app_user_id = ?
        """,
        (result, actual_profit, actual_fta, now, bet_id, app_user_id),
    )
    conn.commit()
    full = conn.execute(
        """
        SELECT id, app_user_id, match_id, league, home_team, away_team,
               team, is_home, kickoff, bookmaker, back_odds, lay_odds,
               stake, commission, lay_stake, liability, fta_pct, notes,
               status, result, actual_profit, actual_fta, created_at, settled_at
        FROM tracked_bets WHERE id = ?
        """,
        (bet_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(full)


def summary(app_user_id):
    ensure_tracked_tables()
    conn = get_db()
    row = conn.execute(
        """
        SELECT
            COUNT(*) as n,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_n,
            SUM(CASE WHEN status = 'settled' THEN 1 ELSE 0 END) as settled_n,
            SUM(COALESCE(actual_profit, 0)) as total_profit,
            SUM(CASE WHEN actual_fta = 1 THEN 1 ELSE 0 END) as fta_hits
        FROM tracked_bets WHERE app_user_id = ?
        """,
        (app_user_id,),
    ).fetchone()
    conn.close()
    return {
        "total": row[0] or 0,
        "open": row[1] or 0,
        "settled": row[2] or 0,
        "total_profit": round(row[3] or 0, 2),
        "fta_hits": row[4] or 0,
    }
