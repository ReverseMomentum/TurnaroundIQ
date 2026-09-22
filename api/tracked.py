"""
Paper-trading tracker for FTA opportunities.

No real money — records hypothetical bets, settles against match_results
when available, and tracks virtual bankroll / ROI.
"""

from datetime import datetime, timezone

from database import get_db

TRACKED_DDL = """
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
    paper INTEGER DEFAULT 1,
    expected_profit REAL,
    created_at TEXT,
    settled_at TEXT
)
"""

PAPER_SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS paper_settings (
    app_user_id TEXT PRIMARY KEY,
    starting_bankroll REAL DEFAULT 1000.0,
    default_stake REAL DEFAULT 40.0,
    default_commission REAL DEFAULT 2.0,
    updated_at TEXT
)
"""


def ensure_tracked_tables():
    conn = get_db()
    conn.execute(TRACKED_DDL)
    conn.execute(PAPER_SETTINGS_DDL)
    cols = {
        r[1] for r in conn.execute("PRAGMA table_info(tracked_bets)").fetchall()
    }
    if "app_user_id" not in cols:
        conn.execute("DROP TABLE IF EXISTS tracked_bets")
        conn.execute(TRACKED_DDL)
        cols = {
            r[1] for r in conn.execute("PRAGMA table_info(tracked_bets)").fetchall()
        }
    for name, typ, default in (
        ("paper", "INTEGER", "1"),
        ("expected_profit", "REAL", "NULL"),
    ):
        if name not in cols:
            conn.execute(
                f"ALTER TABLE tracked_bets ADD COLUMN {name} {typ} DEFAULT {default}"
            )
    conn.commit()
    conn.close()


def get_paper_settings(app_user_id):
    ensure_tracked_tables()
    conn = get_db()
    row = conn.execute(
        "SELECT starting_bankroll, default_stake, default_commission FROM paper_settings WHERE app_user_id = ?",
        (app_user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {
            "starting_bankroll": 1000.0,
            "default_stake": 40.0,
            "default_commission": 2.0,
        }
    return {
        "starting_bankroll": float(row[0] or 1000),
        "default_stake": float(row[1] or 40),
        "default_commission": float(row[2] or 2),
    }


def save_paper_settings(app_user_id, starting_bankroll=None, default_stake=None, default_commission=None):
    ensure_tracked_tables()
    cur = get_paper_settings(app_user_id)
    if starting_bankroll is not None:
        cur["starting_bankroll"] = float(starting_bankroll)
    if default_stake is not None:
        cur["default_stake"] = float(default_stake)
    if default_commission is not None:
        cur["default_commission"] = float(default_commission)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        """
        INSERT OR REPLACE INTO paper_settings
        (app_user_id, starting_bankroll, default_stake, default_commission, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            app_user_id,
            cur["starting_bankroll"],
            cur["default_stake"],
            cur["default_commission"],
            now,
        ),
    )
    conn.commit()
    conn.close()
    return cur


def _row_to_dict(row):
    keys = [
        "id", "app_user_id", "match_id", "league", "home_team", "away_team",
        "team", "is_home", "kickoff", "bookmaker", "back_odds", "lay_odds",
        "stake", "commission", "lay_stake", "liability", "fta_pct", "notes",
        "status", "result", "actual_profit", "actual_fta", "paper",
        "expected_profit", "created_at", "settled_at",
    ]
    # Tolerate older rows without paper/expected_profit
    vals = list(row)
    while len(vals) < len(keys):
        vals.append(None)
    d = dict(zip(keys, vals[: len(keys)]))
    d["match"] = f"{d['home_team']} vs {d['away_team']}"
    d["estimated_lay"] = d.get("lay_odds") is None
    d["source"] = "paper" if d.get("paper") in (1, True, "1") else "manual"
    d["paper"] = bool(d.get("paper") in (1, True, "1", None))
    return d


def _expected_profit(stake, back_odds, fta_pct, commission=2.0):
    """Simple EV if backing FTA at back_odds with stake."""
    try:
        stake = float(stake or 0)
        odds = float(back_odds or 0)
        p = float(fta_pct or 0)
        if p > 1.5:
            p = p / 100.0
        if stake <= 0 or odds <= 1:
            return None
        win = stake * (odds - 1) * (1 - float(commission or 0) / 100.0)
        lose = -stake
        return round(p * win + (1 - p) * lose, 2)
    except (TypeError, ValueError):
        return None


def compute_profit(result, stake, back_odds, commission=2.0, actual_profit=None):
    """
    Paper P&L model (back the FTA selection):
      fta / won  → +stake*(odds-1)*(1-commission)
      no_fta / lost → -stake
      void → 0
    If actual_profit provided, use it.
    """
    if actual_profit is not None:
        return float(actual_profit)
    r = (result or "").lower().strip()
    try:
        stake = float(stake or 0)
        odds = float(back_odds or 0)
        comm = float(commission or 0) / 100.0
    except (TypeError, ValueError):
        return 0.0
    if r in ("void", "push", "cancelled"):
        return 0.0
    if r in ("fta", "won", "win", "hit"):
        if odds > 1:
            return round(stake * (odds - 1) * (1 - comm), 2)
        return 0.0
    if r in ("no_fta", "lost", "lose", "miss"):
        return round(-stake, 2)
    return 0.0


def list_tracked(app_user_id, status=None, limit=50):
    ensure_tracked_tables()
    conn = get_db()
    base = """
        SELECT id, app_user_id, match_id, league, home_team, away_team,
               team, is_home, kickoff, bookmaker, back_odds, lay_odds,
               stake, commission, lay_stake, liability, fta_pct, notes,
               status, result, actual_profit, actual_fta,
               COALESCE(paper, 1), expected_profit, created_at, settled_at
        FROM tracked_bets
        WHERE app_user_id = ?
    """
    if status:
        rows = conn.execute(
            base + " AND status = ? ORDER BY id DESC LIMIT ?",
            (app_user_id, status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            base + " ORDER BY id DESC LIMIT ?",
            (app_user_id, limit),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def create_tracked(app_user_id, data):
    ensure_tracked_tables()
    settings = get_paper_settings(app_user_id)
    now = datetime.now(timezone.utc).isoformat()
    home = (data.get("home_team") or "").strip()
    away = (data.get("away_team") or "").strip()
    team = (data.get("team") or home).strip()
    if not home or not away:
        raise ValueError("home_team and away_team required")

    is_home = 1 if data.get("is_home", team == home) else 0
    back = data.get("back_odds")
    lay = data.get("lay_odds")
    stake = data.get("stake")
    if stake is None:
        stake = settings["default_stake"]
    commission = data.get("commission")
    if commission is None:
        commission = settings["default_commission"]
    fta_pct = data.get("fta_pct")
    exp = _expected_profit(stake, back, fta_pct, commission)
    paper = 1 if data.get("paper", True) else 0

    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO tracked_bets (
            app_user_id, match_id, league, home_team, away_team, team, is_home,
            kickoff, bookmaker, back_odds, lay_odds, stake, commission,
            lay_stake, liability, fta_pct, notes, status, paper, expected_profit,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            data.get("bookmaker") or "Paper",
            back,
            lay,
            stake,
            commission,
            data.get("lay_stake"),
            data.get("liability"),
            fta_pct,
            data.get("notes") or "paper",
            "open",
            paper,
            exp,
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
               status, result, actual_profit, actual_fta,
               COALESCE(paper, 1), expected_profit, created_at, settled_at
        FROM tracked_bets WHERE id = ?
        """,
        (bet_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def settle_tracked(app_user_id, bet_id, result, actual_profit=None, actual_fta=None):
    ensure_tracked_tables()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    row = conn.execute(
        """
        SELECT id, stake, back_odds, commission, actual_fta
        FROM tracked_bets WHERE id = ? AND app_user_id = ?
        """,
        (bet_id, app_user_id),
    ).fetchone()
    if not row:
        conn.close()
        return None

    profit = compute_profit(
        result, row[1], row[2], row[3], actual_profit=actual_profit
    )
    if actual_fta is None:
        r = (result or "").lower()
        if r in ("fta", "won", "win", "hit"):
            actual_fta = 1
        elif r in ("no_fta", "lost", "lose", "miss"):
            actual_fta = 0

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
        (result, profit, actual_fta, now, bet_id, app_user_id),
    )
    conn.commit()
    full = conn.execute(
        """
        SELECT id, app_user_id, match_id, league, home_team, away_team,
               team, is_home, kickoff, bookmaker, back_odds, lay_odds,
               stake, commission, lay_stake, liability, fta_pct, notes,
               status, result, actual_profit, actual_fta,
               COALESCE(paper, 1), expected_profit, created_at, settled_at
        FROM tracked_bets WHERE id = ?
        """,
        (bet_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(full)


def summary(app_user_id):
    ensure_tracked_tables()
    settings = get_paper_settings(app_user_id)
    conn = get_db()
    row = conn.execute(
        """
        SELECT
            COUNT(*) as n,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_n,
            SUM(CASE WHEN status = 'settled' THEN 1 ELSE 0 END) as settled_n,
            SUM(CASE WHEN status = 'settled' THEN COALESCE(actual_profit, 0) ELSE 0 END) as total_profit,
            SUM(CASE WHEN actual_fta = 1 THEN 1 ELSE 0 END) as fta_hits,
            SUM(CASE WHEN status = 'settled' THEN COALESCE(stake, 0) ELSE 0 END) as staked,
            SUM(CASE WHEN status = 'settled' THEN COALESCE(expected_profit, 0) ELSE 0 END) as expected
        FROM tracked_bets WHERE app_user_id = ?
        """,
        (app_user_id,),
    ).fetchone()
    conn.close()
    total_profit = float(row[3] or 0)
    staked = float(row[5] or 0)
    starting = settings["starting_bankroll"]
    bankroll = round(starting + total_profit, 2)
    roi = round(100.0 * total_profit / staked, 2) if staked else None
    return {
        "total": row[0] or 0,
        "open": row[1] or 0,
        "settled": row[2] or 0,
        "total_profit": round(total_profit, 2),
        "fta_hits": row[4] or 0,
        "staked": round(staked, 2),
        "expected_profit": round(float(row[6] or 0), 2),
        "starting_bankroll": starting,
        "bankroll": bankroll,
        "roi_pct": roi,
        "default_stake": settings["default_stake"],
        "default_commission": settings["default_commission"],
        "mode": "paper",
    }


def auto_settle_from_results(app_user_id=None):
    """
    Close open paper bets when match_results has a decisive 2UP/FTA flag
    for the selected team.
    Returns number settled.
    """
    ensure_tracked_tables()
    conn = get_db()
    if app_user_id:
        opens = conn.execute(
            """
            SELECT id, app_user_id, home_team, away_team, team, is_home,
                   stake, back_odds, commission, match_id
            FROM tracked_bets WHERE status = 'open' AND app_user_id = ?
            """,
            (app_user_id,),
        ).fetchall()
    else:
        opens = conn.execute(
            """
            SELECT id, app_user_id, home_team, away_team, team, is_home,
                   stake, back_odds, commission, match_id
            FROM tracked_bets WHERE status = 'open'
            """
        ).fetchall()

    settled = 0
    for row in opens:
        bet_id, uid, home, away, team, is_home, stake, odds, comm, mid = row
        mr = None
        if mid:
            mr = conn.execute(
                """
                SELECT home_2up, away_2up, home_turnaround, away_turnaround
                FROM match_results WHERE match_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (str(mid),),
            ).fetchone()
        if not mr:
            mr = conn.execute(
                """
                SELECT home_2up, away_2up, home_turnaround, away_turnaround
                FROM match_results
                WHERE home_team = ? AND away_team = ?
                ORDER BY id DESC LIMIT 1
                """,
                (home, away),
            ).fetchone()
        if not mr:
            continue

        home_2up, away_2up, home_ta, away_ta = mr
        # Selected team side
        if is_home or (team and team == home):
            went_2up = int(home_2up or 0)
            fta = int(home_ta or 0)
        else:
            went_2up = int(away_2up or 0)
            fta = int(away_ta or 0)

        if not went_2up:
            # Match finished without selected team going 2-up → FTA market void/miss
            result = "no_fta"
            actual_fta = 0
        else:
            result = "fta" if fta else "no_fta"
            actual_fta = 1 if fta else 0

        profit = compute_profit(result, stake, odds, comm)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE tracked_bets SET
                status = 'settled',
                result = ?,
                actual_profit = ?,
                actual_fta = ?,
                settled_at = ?
            WHERE id = ?
            """,
            (result, profit, actual_fta, now, bet_id),
        )
        settled += 1

    conn.commit()
    conn.close()
    return settled
