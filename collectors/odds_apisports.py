#!/usr/bin/env python3
"""
Pre-match Match Winner odds from api-sports (already in our plan, no extra cost).

    python -u collectors/odds_apisports.py                 # games in the next 24h
    python -u collectors/odds_apisports.py --hours 48 --max-calls 100

Only the next 24h matter by default: exchange lay liquidity is thin before that.
Fixtures priced in the last 15 minutes are skipped, so the app's "Refresh odds"
button and the cron job don't pay twice for the same prices.

For every upcoming fixture we store, per side (home / away):
  - best BACK price from UK bookmakers (and which bookmaker)
  - an ESTIMATED exchange LAY price

api-sports has no lay prices, so the lay is estimated: remove the bookmaker
margin to get a fair price (Pinnacle if quoted, else the median of all books),
then add one Betfair price tick, which is where the exchange lay usually sits on
football match odds. The app labels it "est. lay". A real exchange feed (The
Odds API) can replace this later without touching the app.

Budget: 1-2 fixture-list calls + 1 call per fixture, capped by --max-calls, and
the shared client keeps APISPORTS_RESERVE calls untouched.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from constants import SUPPORTED_LEAGUE_IDS
from database import get_db

MATCH_WINNER = 1  # api-sports bet id
MAX_AGE_HOURS = 24  # older prices are ignored by the app

# Bookmakers a UK customer can back with (2UP-style offers live here).
UK_BACK_BOOKS = {
    "bet365", "williamhill", "paddypower", "skybet", "betfred", "betvictor",
    "boylesports", "ladbrokes", "coral", "unibet", "888sport", "betway",
    "10bet", "betfairsportsbook", "sportingbet", "betuk", "midnite", "livescorebet",
}
SHARP_BOOKS = {"pinnacle"}
EXCHANGES = {"betfair", "betfairexchange", "smarkets", "matchbook", "betdaq"}

DDL = """
CREATE TABLE IF NOT EXISTS fixture_odds (
    match_id TEXT PRIMARY KEY,
    kickoff TEXT,
    home_back REAL, home_book TEXT, home_lay_est REAL,
    away_back REAL, away_book TEXT, away_lay_est REAL,
    draw_back REAL,
    fair_source TEXT,
    books_json TEXT,
    updated_at TEXT
)
"""

# Betfair price ladder: (upper bound, tick size)
_LADDER = [(2, 0.01), (3, 0.02), (4, 0.05), (6, 0.1), (10, 0.2), (20, 0.5),
           (30, 1), (50, 2), (100, 5), (1000, 10)]


def _key(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def tick_up(price: float) -> float:
    """Next Betfair ladder price at or above `price` + one tick."""
    for upper, tick in _LADDER:
        if price < upper:
            steps = int(price / tick + 1e-6)
            return round(min((steps + 1) * tick, 1000), 2)
    return 1000.0


def _to_float(v):
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def parse_bookmakers(bookmakers) -> dict:
    """api-sports bookmakers[] -> {name: {"home": x, "draw": y, "away": z}} (Match Winner only)."""
    out = {}
    for bk in bookmakers or []:
        name = bk.get("name") or ""
        for bet in bk.get("bets") or []:
            if bet.get("id") != MATCH_WINNER and (bet.get("name") or "").lower() != "match winner":
                continue
            prices = {}
            for v in bet.get("values") or []:
                side = {"home": "home", "draw": "draw", "away": "away"}.get(str(v.get("value")).lower())
                odd = _to_float(v.get("odd"))
                if side and odd:
                    prices[side] = odd
            if len(prices) == 3:
                out[name] = prices
    return out


def _fair(prices: dict) -> dict:
    """Remove the margin from a home/draw/away set -> fair decimal odds."""
    inv = {k: 1.0 / v for k, v in prices.items()}
    total = sum(inv.values())
    return {k: total / p for k, p in inv.items()}


def summarise(books: dict) -> dict | None:
    """Best UK back + estimated lay for home and away from a parsed bookmaker set."""
    if not books:
        return None
    sharp = [p for n, p in books.items() if _key(n) in SHARP_BOOKS]
    non_exchange = {n: p for n, p in books.items() if _key(n) not in EXCHANGES}
    if sharp:
        fair, source = _fair(sharp[0]), "pinnacle"
    elif non_exchange:
        fairs = [_fair(p) for p in non_exchange.values()]
        fair = {s: statistics.median(f[s] for f in fairs) for s in ("home", "draw", "away")}
        source = f"median of {len(fairs)} books"
    else:
        return None

    uk = {n: p for n, p in books.items() if _key(n) in UK_BACK_BOOKS}
    row = {"fair_source": source}
    for side in ("home", "away"):
        best_name, best = None, None
        for name, p in uk.items():
            if best is None or p[side] > best:
                best_name, best = name, p[side]
        row[f"{side}_back"] = best
        row[f"{side}_book"] = best_name
        row[f"{side}_lay_est"] = tick_up(fair[side])
    draws = [p["draw"] for p in uk.values()]
    row["draw_back"] = max(draws) if draws else None
    return row


def ensure_table(conn):
    conn.execute(DDL)


def save(conn, match_id, kickoff, books):
    row = summarise(books)
    if not row:
        return False
    conn.execute(
        """INSERT OR REPLACE INTO fixture_odds (match_id, kickoff, home_back, home_book,
               home_lay_est, away_back, away_book, away_lay_est, draw_back, fair_source,
               books_json, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (str(match_id), kickoff, row["home_back"], row["home_book"], row["home_lay_est"],
         row["away_back"], row["away_book"], row["away_lay_est"], row["draw_back"],
         row["fair_source"], json.dumps(books), datetime.now(timezone.utc).isoformat()),
    )
    return True


def load_odds(match_ids, max_age_hours=MAX_AGE_HOURS) -> dict:
    """{match_id: row} for fresh stored odds; {} if the table doesn't exist yet."""
    ids = [str(m) for m in match_ids if m]
    if not ids:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    try:
        conn = get_db()
        q = ",".join("?" * len(ids))
        cur = conn.execute(
            f"""SELECT match_id, home_back, home_book, home_lay_est, away_back, away_book,
                       away_lay_est, fair_source, updated_at
                FROM fixture_odds WHERE match_id IN ({q}) AND updated_at >= ?""",
            (*ids, cutoff),
        )
        cols = [d[0] for d in cur.description]
        rows = {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
        conn.close()
        return rows
    except Exception:
        return {}


def side_prices(row, is_home: bool):
    """(back, bookmaker, lay_est, updated_at) for one side, or None if no UK back price."""
    if not row:
        return None
    s = "home" if is_home else "away"
    back = row.get(f"{s}_back")
    if not back:
        return None
    return back, row.get(f"{s}_book"), row.get(f"{s}_lay_est"), row.get("updated_at")


def _parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def upcoming_fixtures(hours, api_get):
    """(fixture_id, kickoff) for supported-league games kicking off in the next `hours`."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)
    dates, day = [], now.date()
    while day <= end.date():
        dates.append(day.isoformat())
        day += timedelta(days=1)
    out, seen = [], set()
    for date in dates:
        payload = api_get("/fixtures", {"date": date, "status": "NS"})
        for fx in payload.get("response") or []:
            if (fx.get("league") or {}).get("id") not in SUPPORTED_LEAGUE_IDS:
                continue
            meta = fx.get("fixture") or {}
            ko = _parse_time(meta.get("date"))
            if ko and now < ko <= end and meta.get("id") not in seen:
                seen.add(meta.get("id"))
                out.append((meta.get("id"), meta.get("date")))
    out.sort(key=lambda x: x[1] or "")  # soonest first, so a capped run covers the next games
    return out, len(dates)


def _recently_priced(conn, minutes):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return {r[0] for r in conn.execute(
        "SELECT match_id FROM fixture_odds WHERE updated_at >= ?", (cutoff,))}


def refresh(hours=24, max_calls=200, skip_minutes=15, log=print):
    """Fetch odds for games in the next `hours`. Returns a summary dict."""
    from collectors.apisports import AuthError, NetworkError, QuotaExhausted, api_get, require_key
    require_key()
    conn = get_db()
    ensure_table(conn)
    summary = {"fixtures": 0, "saved": 0, "no_odds": 0, "skipped_fresh": 0,
               "calls": 0, "stopped": None}
    try:
        fixtures, list_calls = upcoming_fixtures(hours, api_get)
        summary["calls"] += list_calls
        summary["fixtures"] = len(fixtures)
        fresh = _recently_priced(conn, skip_minutes) if skip_minutes else set()
        log(f"{len(fixtures)} fixtures in supported leagues in the next {hours}h")
        for fixture_id, kickoff in fixtures:
            if str(fixture_id) in fresh:
                summary["skipped_fresh"] += 1
                continue
            if summary["calls"] >= max_calls:
                summary["stopped"] = f"max_calls {max_calls}"
                break
            payload = api_get("/odds", {"fixture": fixture_id, "bet": MATCH_WINNER})
            summary["calls"] += 1
            books = {}
            for item in payload.get("response") or []:
                books.update(parse_bookmakers(item.get("bookmakers")))
            if save(conn, fixture_id, kickoff, books):
                summary["saved"] += 1
            else:
                summary["no_odds"] += 1
            conn.commit()
    except (QuotaExhausted, NetworkError, AuthError) as exc:
        summary["stopped"] = str(exc)
    finally:
        conn.commit()
        conn.close()
    log(f"odds saved for {summary['saved']} fixtures, none yet for {summary['no_odds']}, "
        f"{summary['skipped_fresh']} already fresh ({summary['calls']} api calls)"
        + (f" — stopped: {summary['stopped']}" if summary["stopped"] else ""))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--max-calls", type=int, default=200)
    ap.add_argument("--skip-minutes", type=int, default=15,
                    help="skip fixtures priced this recently (0 = refetch all)")
    args = ap.parse_args(argv)
    refresh(args.hours, args.max_calls, args.skip_minutes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
