#!/usr/bin/env python3
"""
In-play Betfair price log for our football games (for testing lay-the-draw ideas
with real prices: scripts/inplay_drift_report.py).

Run every minute by cron. Each run:
  1. picks the games in exchange_odds (matched to Betfair by collectors/betfair_football.py)
     kicking off from 10 minutes ago... 2.5 hours ago, plus those starting in the next 10 minutes
  2. one listMarketBook call per 40 markets: home / draw / away best back + lay and sizes
  3. if any are in play: one api-sports /fixtures?live=all call for the score and minute
  4. one row per game into inplay_prices

Nothing is called when no game is in that window. Prices come from the delayed
Betfair key, so they can lag the real market by up to a few minutes: fine for
"how far did the draw drift after a goal", not for timing a real trade.

    venv/bin/python -u collectors/betfair_inplay.py
cron: * * * * *  $J betfair_inplay python -u collectors/betfair_inplay.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db  # noqa: E402

BEFORE_KO = timedelta(minutes=10)
AFTER_KO = timedelta(minutes=150)
DRAW_SELECTION = 58805      # Betfair's "The Draw" selection id in every Match Odds market

DDL = """
CREATE TABLE IF NOT EXISTS inplay_prices (
    id INTEGER PRIMARY KEY,
    match_id TEXT NOT NULL,
    market_id TEXT,
    ts TEXT NOT NULL,
    kickoff TEXT,
    inplay INTEGER,
    status TEXT,
    minute INTEGER,
    home_goals INTEGER,
    away_goals INTEGER,
    home_back REAL, home_lay REAL,
    draw_back REAL, draw_back_size REAL, draw_lay REAL, draw_lay_size REAL,
    away_back REAL, away_lay REAL,
    total_matched REAL
)
"""
RUNNERS_DDL = """
CREATE TABLE IF NOT EXISTS inplay_runners (
    market_id TEXT NOT NULL, selection_id INTEGER NOT NULL, side TEXT NOT NULL,
    PRIMARY KEY (market_id, selection_id)
)
"""


def ensure_tables(conn):
    conn.execute(DDL)
    conn.execute(RUNNERS_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inplay_match ON inplay_prices(match_id, ts)")


def games_to_watch(conn, now):
    """[(match_id, market_id, kickoff)] in the logging window."""
    try:
        rows = conn.execute("SELECT match_id, market_id, kickoff FROM exchange_odds "
                            "WHERE market_id IS NOT NULL AND kickoff IS NOT NULL").fetchall()
    except Exception:
        return []
    out = []
    for mid, market, ko in rows:
        try:
            k = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except ValueError:
            continue
        if k.tzinfo is None:
            k = k.replace(tzinfo=timezone.utc)
        if k - BEFORE_KO <= now <= k + AFTER_KO:
            out.append((str(mid), market, k.isoformat()))
    return out


def runner_sides(conn, client, market_ids):
    """{market_id: {selection_id: home|draw|away}}, from the catalogue once per market."""
    known = {}
    for m, sel, side in conn.execute("SELECT market_id, selection_id, side FROM inplay_runners"):
        known.setdefault(m, {})[sel] = side
    missing = [m for m in market_ids if m not in known]
    for i in range(0, len(missing), 50):
        for cat in client.call("listMarketCatalogue", {
                "filter": {"marketIds": missing[i:i + 50]},
                "marketProjection": ["RUNNER_DESCRIPTION"], "maxResults": 100}):
            for r in cat.get("runners") or []:
                side = {1: "home", 2: "away", 3: "draw"}.get(r.get("sortPriority"))
                if r.get("selectionId") == DRAW_SELECTION:
                    side = "draw"
                if side:
                    known.setdefault(cat["marketId"], {})[r["selectionId"]] = side
                    conn.execute("INSERT OR REPLACE INTO inplay_runners VALUES (?,?,?)",
                                 (cat["marketId"], r["selectionId"], side))
    return known


def prices(book, sides):
    """{home|draw|away: (back, back_size, lay, lay_size)} from a market book."""
    out = {}
    for r in (book or {}).get("runners") or []:
        side = sides.get(r.get("selectionId")) or ("draw" if r.get("selectionId") == DRAW_SELECTION else None)
        if not side:
            continue
        ex = r.get("ex") or {}
        b = (ex.get("availableToBack") or [{}])[0]
        lay = (ex.get("availableToLay") or [{}])[0]
        out[side] = (b.get("price"), b.get("size"), lay.get("price"), lay.get("size"))
    return out


def live_scores():
    """{api-sports fixture id: (minute, home_goals, away_goals, status)} (one call)."""
    from api.live_monitor import _get
    out = {}
    for item in (_get("/fixtures", {"live": "all"}).get("response") or []):
        fx, goals = item.get("fixture") or {}, item.get("goals") or {}
        st = fx.get("status") or {}
        out[str(fx.get("id"))] = (st.get("elapsed"), goals.get("home"), goals.get("away"), st.get("short"))
    return out


def run(client=None, now=None, scores=None, log=print):
    now = now or datetime.now(timezone.utc)
    conn = get_db()
    try:
        ensure_tables(conn)
        games = games_to_watch(conn, now)
        if not games:
            conn.commit()
            return 0
        from collectors import betfair
        if client is None:
            if not betfair.configured():
                log("Betfair not configured")
                return 0
            client = betfair.Client()
        markets = sorted({m for _, m, _ in games})
        sides = runner_sides(conn, client, markets)
        books = betfair.books(client, markets)
        inplay_any = any((books.get(m) or {}).get("inplay") for m in markets)
        if scores is None:
            try:
                scores = live_scores() if inplay_any else {}
            except Exception as exc:   # no score this minute: prices are still worth keeping
                log(f"api-sports live call failed: {exc}")
                scores = {}
        ts = now.isoformat(timespec="seconds")
        n = 0
        for mid, market, ko in games:
            book = books.get(market)
            if not book or book.get("status") == "CLOSED":
                continue
            p = prices(book, sides.get(market) or {})
            h, d, a = (p.get(k, (None,) * 4) for k in ("home", "draw", "away"))
            minute, hg, ag, _st = scores.get(mid, (None, None, None, None))
            conn.execute(
                """INSERT INTO inplay_prices (match_id, market_id, ts, kickoff, inplay, status, minute,
                       home_goals, away_goals, home_back, home_lay, draw_back, draw_back_size,
                       draw_lay, draw_lay_size, away_back, away_lay, total_matched)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, market, ts, ko, int(bool(book.get("inplay"))), book.get("status"), minute, hg, ag,
                 h[0], h[2], d[0], d[1], d[2], d[3], a[0], a[2], book.get("totalMatched")))
            n += 1
        conn.commit()
        log(f"{now:%H:%M} logged {n} of {len(games)} games ({sum(1 for m in markets if (books.get(m) or {}).get('inplay'))} in play)")
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    run()
