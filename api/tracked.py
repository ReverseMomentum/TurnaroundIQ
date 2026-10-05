"""
Paper-trading tracker for FTA, Early Goal Hunter, and Chaos Factor.

No real money — records hypothetical bets, settles against match_results
when available, and tracks virtual bankroll / ROI by product and FTA band.
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
    product TEXT DEFAULT 'fta',
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

# FTA% is the FULL event: goes 2 up AND fails to win (typically 1–5%).
FTA_BANDS = [
    ("elite_4plus", 4.0, 100.0),
    ("high_3_4", 3.0, 4.0),
    ("mid_2_3", 2.0, 3.0),
    ("low_1_2", 1.0, 2.0),
    ("micro_under_1", 0.0, 1.0),
]

SELECT_COLS = """
    id, app_user_id, match_id, league, home_team, away_team,
    team, is_home, kickoff, bookmaker, back_odds, lay_odds,
    stake, commission, lay_stake, liability, fta_pct, notes,
    status, result, actual_profit, actual_fta,
    COALESCE(paper, 1), expected_profit,
    COALESCE(product, 'fta'), created_at, settled_at,
    ew_places, ew_fraction, p_win, p_place
"""


def fta_pct_as_percent(val) -> float:
    """fta_pct is always stored/served as percent. No fraction guessing:
    full-event values below 1% are normal and must not become 80%."""
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def fta_band(val) -> str:
    pct = fta_pct_as_percent(val)
    for name, lo, hi in FTA_BANDS:
        if lo <= pct < hi or (hi >= 100 and pct >= lo):
            return name
    return "micro_under_1"


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
        ("product", "TEXT", "'fta'"),
        # The Stables (each-way racing): places paid, fraction, model chances
        ("ew_places", "INTEGER", "NULL"),
        ("ew_fraction", "REAL", "NULL"),
        ("p_win", "REAL", "NULL"),
        ("p_place", "REAL", "NULL"),
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
        "expected_profit", "product", "created_at", "settled_at",
        "ew_places", "ew_fraction", "p_win", "p_place",
    ]
    vals = list(row)
    while len(vals) < len(keys):
        vals.append(None)
    d = dict(zip(keys, vals[: len(keys)]))
    d["match"] = f"{d['home_team']} vs {d['away_team']}"
    d["estimated_lay"] = d.get("lay_odds") is None
    d["product"] = d.get("product") or "fta"
    d["source"] = "paper" if d.get("paper") in (1, True, "1") else "manual"
    d["paper"] = bool(d.get("paper") in (1, True, "1", None))
    d["fta_band"] = fta_band(d.get("fta_pct"))
    d["fta_pct_display"] = round(fta_pct_as_percent(d.get("fta_pct")), 2)
    return d


def _estimate_lay(back_odds):
    """Same margin as opportunities_engine.estimate_lay_odds."""
    margin = 0.03 if back_odds < 2 else 0.05 if back_odds < 5 else 0.08
    return round(back_odds * (1 + margin), 2)


def matched_bet_outcomes(stake, back_odds, lay_odds=None, commission=2.0):
    """
    2UP / FTA matched bet (back at the bookie + lay at the exchange).
    Returns (qualifying_loss, fta_profit):
      - team goes 2 up and fails to win -> fta_profit (early payout + lay wins)
      - anything else                  -> qualifying_loss (small, usually negative)
    Same formulas as calculations.py and the app's calculator.
    """
    from calculations import (
        calculate_fta_profit, calculate_lay_stake, calculate_qualifying_loss,
    )
    try:
        stake = float(stake or 0)
        back = float(back_odds or 0)
        comm = float(commission if commission is not None else 2.0)
        lay = float(lay_odds) if lay_odds else _estimate_lay(back)
    except (TypeError, ValueError):
        return None, None
    if stake <= 0 or back <= 1 or lay <= 1:
        return None, None
    lay_stake = calculate_lay_stake(back, lay, stake, comm)
    ql = calculate_qualifying_loss(back, lay, stake, lay_stake, comm)
    fta = calculate_fta_profit(stake, back, lay_stake, comm)
    return ql, fta


def _lay_parts(lay_odds, lay_stake, commission):
    """(lay loses if the horse wins, lay wins otherwise) for an exchange win lay; (0, 0) without one."""
    try:
        lo, ls, cm = float(lay_odds or 0), float(lay_stake or 0), float(commission or 0) / 100.0
    except (TypeError, ValueError):
        return 0.0, 0.0
    if lo <= 1 or ls <= 0:
        return 0.0, 0.0
    return -ls * (lo - 1), ls * (1 - cm)


def ew_returns(result, stake, odds, fraction, lay_odds=None, lay_stake=None, commission=0.0):
    """Profit of an each-way bet (stake = total, half win / half place), plus an optional win lay."""
    try:
        stake, odds, fraction = float(stake or 0), float(odds or 0), float(fraction or 0)
    except (TypeError, ValueError):
        return 0.0
    half = stake / 2
    place_odds = 1 + (odds - 1) * fraction
    lay_if_win, lay_if_not = _lay_parts(lay_odds, lay_stake, commission)
    r = (result or "").lower()
    if r in ("won", "win"):
        return round(half * (odds - 1) + half * (place_odds - 1) + lay_if_win, 2)
    if r == "placed":
        return round(-half + half * (place_odds - 1) + lay_if_not, 2)
    if r in ("lost", "lose", "unplaced"):
        return round(-stake + lay_if_not, 2)
    return 0.0


def ew_expected(stake, odds, fraction, p_win, p_place, lay_odds=None, lay_stake=None, commission=0.0):
    try:
        stake, odds, fraction = float(stake), float(odds), float(fraction)
        p_win, p_place = float(p_win), float(p_place)
    except (TypeError, ValueError):
        return None
    place_odds = 1 + (odds - 1) * fraction
    lay_if_win, lay_if_not = _lay_parts(lay_odds, lay_stake, commission)
    return round(stake / 2 * (p_win * odds - 1) + stake / 2 * (p_place * place_odds - 1)
                 + p_win * lay_if_win + (1 - p_win) * lay_if_not, 2)


def ew_lay_stake(stake, odds, lay_odds, commission, lay_pct) -> tuple:
    """
    Win lay on the exchange for an each-way bet. Full lay (100%) covers the win
    half: the win half then makes about the same whether the horse wins or not,
    leaving mainly the place half riding. Part lay = that share of it.
    Returns (lay_stake, liability) or (None, None) for no lay.
    """
    try:
        stake, odds, lay_odds = float(stake), float(odds), float(lay_odds or 0)
        cm, pct = float(commission or 0) / 100.0, float(lay_pct or 0) / 100.0
    except (TypeError, ValueError):
        return None, None
    if pct <= 0 or lay_odds <= 1 or lay_odds - cm <= 0:
        return None, None
    ls = round(min(pct, 1.0) * (stake / 2) * odds / (lay_odds - cm), 2)
    return ls, round(ls * (lay_odds - 1), 2)


def _expected_profit(stake, back_odds, fta_pct, commission=2.0, lay_odds=None, product="fta"):
    """fta_pct is always percent (full event for FTA, e.g. 2.4)."""
    try:
        p = float(fta_pct or 0) / 100.0
    except (TypeError, ValueError):
        return None
    if (product or "fta") == "fta":
        ql, fta = matched_bet_outcomes(stake, back_odds, lay_odds, commission)
        if ql is None:
            return None
        return round(fta * p - abs(ql) * (1 - p), 2)
    try:
        stake = float(stake or 0)
        odds = float(back_odds or 0)
        if stake <= 0 or odds <= 1:
            return None
        win = stake * (odds - 1) * (1 - float(commission or 0) / 100.0)
        return round(p * win - (1 - p) * stake, 2)
    except (TypeError, ValueError):
        return None


def compute_profit(result, stake, back_odds, commission=2.0, actual_profit=None,
                   lay_odds=None, product="fta", ew_fraction=None, lay_stake=None):
    if actual_profit is not None:
        return float(actual_profit)
    if (product or "fta") == "stables":
        return ew_returns(result, stake, back_odds, ew_fraction, lay_odds, lay_stake, commission)
    r = (result or "").lower().strip()
    if r in ("void", "push", "cancelled"):
        return 0.0
    hit = r in ("fta", "won", "win", "hit")
    miss = r in ("no_fta", "lost", "lose", "miss")
    if not (hit or miss):
        return 0.0
    if (product or "fta") == "fta":
        ql, fta = matched_bet_outcomes(stake, back_odds, lay_odds, commission)
        if ql is None:
            return 0.0
        return round(fta if hit else ql, 2)
    # Early Goal / Chaos: simple back bet on the signal
    try:
        stake = float(stake or 0)
        odds = float(back_odds or 0)
        comm = float(commission or 0) / 100.0
    except (TypeError, ValueError):
        return 0.0
    if hit:
        return round(stake * (odds - 1) * (1 - comm), 2) if odds > 1 else 0.0
    return round(-stake, 2)


def list_tracked(app_user_id, status=None, limit=50):
    ensure_tracked_tables()
    conn = get_db()
    base = f"SELECT {SELECT_COLS} FROM tracked_bets WHERE app_user_id = ?"
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
    product = (data.get("product") or "fta").strip().lower()
    exp = _expected_profit(stake, back, fta_pct, commission, lay_odds=lay, product=product)
    if product == "stables":
        # optional win lay on the exchange (lay_odds + lay_stake), no FTA-style lay
        lay = data.get("lay_odds") if data.get("lay_stake") else None
        exp = ew_expected(stake, back, data.get("ew_fraction"), data.get("p_win"), data.get("p_place"),
                          lay, data.get("lay_stake"), commission)
    paper = 1 if data.get("paper", True) else 0

    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO tracked_bets (
            app_user_id, match_id, league, home_team, away_team, team, is_home,
            kickoff, bookmaker, back_odds, lay_odds, stake, commission,
            lay_stake, liability, fta_pct, notes, status, paper, expected_profit,
            product, created_at, ew_places, ew_fraction, p_win, p_place
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            product,
            now,
            data.get("ew_places"),
            data.get("ew_fraction"),
            data.get("p_win"),
            data.get("p_place"),
        ),
    )
    bet_id = cur.lastrowid
    conn.commit()
    row = conn.execute(
        f"SELECT {SELECT_COLS} FROM tracked_bets WHERE id = ?",
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
        SELECT id, stake, back_odds, commission, actual_fta, lay_odds,
               COALESCE(product, 'fta'), ew_fraction, lay_stake
        FROM tracked_bets WHERE id = ? AND app_user_id = ?
        """,
        (bet_id, app_user_id),
    ).fetchone()
    if not row:
        conn.close()
        return None

    profit = compute_profit(
        result, row[1], row[2], row[3], actual_profit=actual_profit,
        lay_odds=row[5], product=row[6], ew_fraction=row[7],
        lay_stake=row[8] if row[6] == "stables" else None,
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
        f"SELECT {SELECT_COLS} FROM tracked_bets WHERE id = ?",
        (bet_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(full)


EDITABLE = ("stake", "back_odds", "lay_odds", "commission", "bookmaker", "notes")


def update_tracked(app_user_id, bet_id, changes):
    """Edit a tracked bet. Lay stake, liability and expected profit are recomputed;
    a settled bet keeps its result and its profit is recomputed from the new prices."""
    ensure_tracked_tables()
    conn = get_db()
    row = conn.execute(
        f"SELECT {SELECT_COLS} FROM tracked_bets WHERE id = ? AND app_user_id = ?",
        (bet_id, app_user_id),
    ).fetchone()
    if not row:
        conn.close()
        return None
    bet = _row_to_dict(row)
    bet.update({k: v for k, v in (changes or {}).items() if k in EDITABLE and v is not None})

    stake, back, comm = float(bet["stake"] or 0), float(bet["back_odds"] or 0), float(bet["commission"] or 0)
    lay = float(bet["lay_odds"]) if bet.get("lay_odds") else _estimate_lay(back) if back > 1 else None
    lay_stake = liability = None
    if lay and lay - comm / 100 > 0:
        lay_stake = round(back * stake / (lay - comm / 100), 2)
        liability = round((lay - 1) * lay_stake, 2)
    exp = _expected_profit(stake, back, bet.get("fta_pct"), comm, lay_odds=bet.get("lay_odds"),
                           product=bet["product"])
    if bet["product"] == "stables":
        lay_stake, liability = bet.get("lay_stake"), bet.get("liability")
        if lay_stake and bet.get("lay_odds"):     # odds edited: keep the lay stake, refresh the liability
            liability = round(float(lay_stake) * (float(bet["lay_odds"]) - 1), 2)
        exp = ew_expected(stake, back, bet.get("ew_fraction"), bet.get("p_win"), bet.get("p_place"),
                          bet.get("lay_odds"), lay_stake, comm)
    profit = bet.get("actual_profit")
    # a traded-out bet's profit is what the user really got: keep it
    if bet["status"] == "settled" and bet.get("result") and bet["result"] != "traded":
        profit = compute_profit(bet["result"], stake, back, comm, lay_odds=bet.get("lay_odds"),
                                product=bet["product"], ew_fraction=bet.get("ew_fraction"),
                                lay_stake=lay_stake if bet["product"] == "stables" else None)
    conn.execute(
        """UPDATE tracked_bets SET stake=?, back_odds=?, lay_odds=?, commission=?, bookmaker=?,
               notes=?, lay_stake=?, liability=?, expected_profit=?, actual_profit=?
           WHERE id = ? AND app_user_id = ?""",
        (stake, back, bet.get("lay_odds"), comm, bet.get("bookmaker"), bet.get("notes"),
         lay_stake, liability, exp, profit, bet_id, app_user_id),
    )
    conn.commit()
    full = conn.execute(f"SELECT {SELECT_COLS} FROM tracked_bets WHERE id = ?", (bet_id,)).fetchone()
    conn.close()
    return _row_to_dict(full)


def delete_tracked(app_user_id, bet_id):
    ensure_tracked_tables()
    conn = get_db()
    cur = conn.execute("DELETE FROM tracked_bets WHERE id = ? AND app_user_id = ?", (bet_id, app_user_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


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
        "by_band": summary_by_fta_band(app_user_id),
        "by_product": summary_by_product(app_user_id),
    }


def summary_by_fta_band(app_user_id):
    ensure_tracked_tables()
    bets = [b for b in list_tracked(app_user_id, limit=5000) if (b.get("product") or "fta") == "fta"]
    out = {}
    for name, lo, hi in FTA_BANDS:
        out[name] = {
            "range": f"{lo}-{hi}%",
            "n": 0, "open": 0, "settled": 0, "fta_hits": 0,
            "staked": 0.0, "profit": 0.0, "roi_pct": None, "hit_rate": None,
        }
    for b in bets:
        band = b.get("fta_band") or fta_band(b.get("fta_pct"))
        if band not in out:
            out[band] = {
                "range": band, "n": 0, "open": 0, "settled": 0, "fta_hits": 0,
                "staked": 0.0, "profit": 0.0, "roi_pct": None, "hit_rate": None,
            }
        bucket = out[band]
        bucket["n"] += 1
        if b.get("status") == "open":
            bucket["open"] += 1
        if b.get("status") == "settled":
            bucket["settled"] += 1
            bucket["staked"] += float(b.get("stake") or 0)
            bucket["profit"] += float(b.get("actual_profit") or 0)
            if b.get("actual_fta") == 1:
                bucket["fta_hits"] += 1
    for bucket in out.values():
        bucket["staked"] = round(bucket["staked"], 2)
        bucket["profit"] = round(bucket["profit"], 2)
        if bucket["staked"]:
            bucket["roi_pct"] = round(100.0 * bucket["profit"] / bucket["staked"], 2)
        if bucket["settled"]:
            bucket["hit_rate"] = round(100.0 * bucket["fta_hits"] / bucket["settled"], 1)
    return out


def summary_by_product(app_user_id):
    ensure_tracked_tables()
    bets = list_tracked(app_user_id, limit=5000)
    out = {}
    for b in bets:
        prod = b.get("product") or "fta"
        if prod not in out:
            out[prod] = {
                "n": 0, "open": 0, "settled": 0, "hits": 0,
                "staked": 0.0, "profit": 0.0, "roi_pct": None, "hit_rate": None,
            }
        bucket = out[prod]
        bucket["n"] += 1
        if b.get("status") == "open":
            bucket["open"] += 1
        if b.get("status") == "settled":
            bucket["settled"] += 1
            bucket["staked"] += float(b.get("stake") or 0)
            bucket["profit"] += float(b.get("actual_profit") or 0)
            if b.get("actual_fta") == 1:
                bucket["hits"] += 1
    for bucket in out.values():
        bucket["staked"] = round(bucket["staked"], 2)
        bucket["profit"] = round(bucket["profit"], 2)
        if bucket["staked"]:
            bucket["roi_pct"] = round(100.0 * bucket["profit"] / bucket["staked"], 2)
        if bucket["settled"]:
            bucket["hit_rate"] = round(100.0 * bucket["hits"] / bucket["settled"], 1)
    return out


def _fetch_match_row(conn, mid, home, away):
    mr = None
    if mid:
        mr = conn.execute(
            """
            SELECT home_2up, away_2up, home_turnaround, away_turnaround,
                   home_early_goal, away_early_goal, final_home, final_away
            FROM match_results WHERE match_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (str(mid),),
        ).fetchone()
    if not mr:
        mr = conn.execute(
            """
            SELECT home_2up, away_2up, home_turnaround, away_turnaround,
                   home_early_goal, away_early_goal, final_home, final_away
            FROM match_results
            WHERE home_team = ? AND away_team = ?
            ORDER BY id DESC LIMIT 1
            """,
            (home, away),
        ).fetchone()
    return mr


def auto_settle_from_results(app_user_id=None):
    """
    Settle open paper bets:
      fta        → 2UP then fail to win
      early_goal → either side scored early (home_early_goal / away_early_goal)
      chaos      → final score BTTS and O2.5 (high-chaos proxy hit)
    """
    ensure_tracked_tables()
    conn = get_db()
    if app_user_id:
        opens = conn.execute(
            """
            SELECT id, app_user_id, home_team, away_team, team, is_home,
                   stake, back_odds, commission, match_id, lay_odds,
                   COALESCE(product, 'fta')
            FROM tracked_bets WHERE status = 'open' AND app_user_id = ?
            """,
            (app_user_id,),
        ).fetchall()
    else:
        opens = conn.execute(
            """
            SELECT id, app_user_id, home_team, away_team, team, is_home,
                   stake, back_odds, commission, match_id, lay_odds,
                   COALESCE(product, 'fta')
            FROM tracked_bets WHERE status = 'open'
            """
        ).fetchall()

    settled = 0
    for row in opens:
        bet_id, uid, home, away, team, is_home, stake, odds, comm, mid, lay, product = row
        if (product or "").lower() == "stables":  # racing bets settle from racing results (racing/bets.py)
            continue
        mr = _fetch_match_row(conn, mid, home, away)
        if not mr:
            continue

        home_2up, away_2up, home_ta, away_ta, home_eg, away_eg, fh, fa = mr
        product = (product or "fta").lower()

        if product == "early_goal":
            hit = int(home_eg or 0) == 1 or int(away_eg or 0) == 1
            result = "won" if hit else "lost"
            actual_fta = 1 if hit else 0
        elif product == "chaos":
            try:
                fh_i, fa_i = int(fh or 0), int(fa or 0)
            except (TypeError, ValueError):
                continue
            btts = fh_i > 0 and fa_i > 0
            o25 = (fh_i + fa_i) >= 3
            hit = btts and o25
            result = "won" if hit else "lost"
            actual_fta = 1 if hit else 0
        else:
            # FTA default
            if is_home or (team and team == home):
                went_2up = int(home_2up or 0)
                fta = int(home_ta or 0)
            else:
                went_2up = int(away_2up or 0)
                fta = int(away_ta or 0)
            if not went_2up:
                result = "no_fta"
                actual_fta = 0
            else:
                result = "fta" if fta else "no_fta"
                actual_fta = 1 if fta else 0

        profit = compute_profit(result, stake, odds, comm, lay_odds=lay, product=product)
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
