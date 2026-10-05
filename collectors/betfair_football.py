#!/usr/bin/env python3
"""
Real exchange prices for the football picks: best back / lay (and the money
waiting at that price) on Betfair's Match Odds market, for every game in our
leagues kicking off in the next 24 hours.

Uses the same Betfair login as The Stables (collectors/betfair.py: app key,
username, password, and the UK proxy). The free "delayed" key is enough:
prices lag the live exchange slightly, so this is a guide to how close back
and lay are, not a price to bet blind on.

    python -u collectors/betfair_football.py            # next 24h
    python -u collectors/betfair_football.py --hours 6

Betfair names teams its own way ("Sheff Utd U21", "Bolton Res"), so each
Betfair market is matched to an api-sports fixture by kick-off time (within
15 minutes) plus team-name similarity, and youth/reserve sides only ever match
youth/reserve sides.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db  # noqa: E402

SOCCER = "1"
# Countries of our leagues (GB covers England + Scotland on Betfair)
COUNTRIES = ["GB", "DE", "ES", "IT", "FR", "NL", "BE", "PT", "US", "DK", "NO", "SE", "IE",
             "TR", "AT", "CH", "BR", "RU"]
CATALOGUE_PAGE = 200     # RUNNER_DESCRIPTION costs 1 point per market, limit 200
BOOK_PAGE = 40           # EX_BEST_OFFERS costs 5 points per market, limit 200
KICKOFF_SLACK = timedelta(minutes=15)
MIN_SIDE_SCORE = 0.62
MAX_AGE_HOURS = 3        # older prices are not shown

DDL = """
CREATE TABLE IF NOT EXISTS exchange_odds (
    match_id TEXT PRIMARY KEY,
    market_id TEXT,
    betfair_event TEXT,
    home_back REAL, home_back_size REAL, home_lay REAL, home_lay_size REAL,
    away_back REAL, away_back_size REAL, away_lay REAL, away_lay_size REAL,
    total_matched REAL,
    updated_at TEXT
)
"""

ABBREV = {
    "utd": "united", "u": "united", "wed": "wednesday", "sheff": "sheffield", "man": "manchester",
    "nottm": "nottingham", "nott": "nottingham", "qpr": "queens park rangers", "wolves": "wolverhampton",
    "brighton": "brighton hove albion", "spurs": "tottenham", "res": "reserves", "st": "saint",
    "ath": "athletic", "atl": "atletico", "bor": "borussia", "mgladbach": "monchengladbach",
    "gladbach": "monchengladbach", "psv": "psv eindhoven", "munich": "munchen", "cologne": "koln",
    "koeln": "koln", "muenchen": "munchen", "lisbon": "cp",
}
FILLER = {"fc", "afc", "cf", "sc", "ac", "the", "and", "&", "club", "football", "hove", "albion"}
YOUTH = re.compile(r"\b(u ?1[6-9]|u ?2[0-3]|res|reserves|jong|ii|b)\b", re.I)


def is_youth(name: str) -> bool:
    return bool(YOUTH.search(name or ""))


def _tokens(name: str) -> list[str]:
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    out = []
    for w in s.split():
        w = ABBREV.get(w, w)
        out.extend(w.split())
    return [w for w in out if w not in FILLER and not re.fullmatch(r"u?\d{2}|u|res|reserves|jong|ii|b", w)]


def name_score(a: str, b: str) -> float:
    """0..1 similarity of two team names after expanding abbreviations."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    ja, jb = " ".join(ta), " ".join(tb)
    if ja == jb:
        return 1.0
    sa, sb = set(ta), set(tb)
    seq = SequenceMatcher(None, ja, jb).ratio()
    if (sa - sb) and (sb - sa) and seq < 0.9:
        # each name has its own distinguishing word (Sheffield UNITED vs Sheffield
        # WEDNESDAY): different clubs, unless it is just a spelling variant
        return 0.0
    overlap = len(sa & sb) / min(len(sa), len(sb))
    prefix = 1.0 if (ja.startswith(jb) or jb.startswith(ja)) else 0.0
    return max(seq, overlap * 0.95, prefix * 0.9)


def _split_event(name: str):
    parts = re.split(r"\s+v(?:s\.?)?\s+", name or "", maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (None, None)


def match_markets(markets, fixtures):
    """{match_id: market} pairing Betfair Match Odds markets with our fixtures."""
    out = {}
    for fx in fixtures:
        ko = fx["kickoff"]
        best, best_score = None, 0.0
        for m in markets:
            try:
                start = datetime.fromisoformat(m["marketStartTime"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if abs(start - ko) > KICKOFF_SLACK:
                continue
            h, a = _split_event((m.get("event") or {}).get("name"))
            if not h:
                continue
            if is_youth(h) != is_youth(fx["home"]) or is_youth(a) != is_youth(fx["away"]):
                continue
            sh, sa = name_score(h, fx["home"]), name_score(a, fx["away"])
            if min(sh, sa) < MIN_SIDE_SCORE:
                continue
            if sh + sa > best_score:
                best, best_score = m, sh + sa
        if best is not None:
            out[str(fx["match_id"])] = best
    return out


def our_fixtures(hours, api_get):
    """api-sports fixtures in our leagues kicking off in the next `hours` (1-2 calls)."""
    from constants import SUPPORTED_LEAGUE_IDS
    from team_normalizer import normalize_team
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)
    day, out, seen = now.date(), [], set()
    while day <= end.date():
        for fx in api_get("/fixtures", {"date": day.isoformat(), "status": "NS"}).get("response") or []:
            if (fx.get("league") or {}).get("id") not in SUPPORTED_LEAGUE_IDS:
                continue
            meta, teams = fx.get("fixture") or {}, fx.get("teams") or {}
            try:
                ko = datetime.fromisoformat(str(meta.get("date")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if now < ko <= end and meta.get("id") not in seen:
                seen.add(meta.get("id"))
                out.append({"match_id": meta.get("id"), "kickoff": ko,
                            "home": normalize_team((teams.get("home") or {}).get("name") or ""),
                            "away": normalize_team((teams.get("away") or {}).get("name") or "")})
        day += timedelta(days=1)
    return out


def match_odds_markets(client, hours, now=None):
    """Every Betfair soccer Match Odds market in our countries starting within `hours`."""
    from collectors.betfair import _iso
    now = now or datetime.now(timezone.utc)
    until = now + timedelta(hours=hours)
    out, seen, start = [], set(), now
    for _ in range(30):
        page = client.call("listMarketCatalogue", {
            "filter": {"eventTypeIds": [SOCCER], "marketCountries": COUNTRIES,
                       "marketTypeCodes": ["MATCH_ODDS"],
                       "marketStartTime": {"from": _iso(start), "to": _iso(until)}},
            "marketProjection": ["EVENT", "COMPETITION", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
            "sort": "FIRST_TO_START",
            "maxResults": CATALOGUE_PAGE,
        })
        new = [m for m in page if m["marketId"] not in seen]
        for m in new:
            seen.add(m["marketId"])
        out.extend(new)
        if len(page) < CATALOGUE_PAGE or not new:
            break
        start = datetime.fromisoformat(page[-1]["marketStartTime"].replace("Z", "+00:00"))
    return out


def side_prices(market, book):
    """{home|away: (back, back_size, lay, lay_size)} from a market book.
    Runners: sortPriority 1 = home, 2 = away, 3 = the draw."""
    by_sel = {r["selectionId"]: r for r in (book or {}).get("runners") or []}
    out = {}
    for rd in market.get("runners") or []:
        side = {1: "home", 2: "away"}.get(rd.get("sortPriority"))
        r = by_sel.get(rd.get("selectionId"))
        if not side or not r or r.get("status") not in (None, "ACTIVE"):
            continue
        ex = r.get("ex") or {}
        b = (ex.get("availableToBack") or [{}])[0]
        lay = (ex.get("availableToLay") or [{}])[0]
        out[side] = (b.get("price"), b.get("size"), lay.get("price"), lay.get("size"))
    return out


def save(conn, match_id, market, book, prices, ts):
    h = prices.get("home", (None,) * 4)
    a = prices.get("away", (None,) * 4)
    conn.execute(
        """INSERT INTO exchange_odds (match_id, market_id, betfair_event, home_back, home_back_size,
               home_lay, home_lay_size, away_back, away_back_size, away_lay, away_lay_size,
               total_matched, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(match_id) DO UPDATE SET market_id=excluded.market_id,
               betfair_event=excluded.betfair_event, home_back=excluded.home_back,
               home_back_size=excluded.home_back_size, home_lay=excluded.home_lay,
               home_lay_size=excluded.home_lay_size, away_back=excluded.away_back,
               away_back_size=excluded.away_back_size, away_lay=excluded.away_lay,
               away_lay_size=excluded.away_lay_size, total_matched=excluded.total_matched,
               updated_at=excluded.updated_at""",
        (str(match_id), market["marketId"], (market.get("event") or {}).get("name"),
         *h, *a, (book or {}).get("totalMatched"), ts),
    )


def ensure_table(conn):
    conn.execute(DDL)


def load(match_ids, max_age_hours=MAX_AGE_HOURS):
    """{match_id: row} of fresh exchange prices (empty if none / table missing)."""
    ids = [str(m) for m in match_ids if m]
    if not ids:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    conn = get_db()
    try:
        ensure_table(conn)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(exchange_odds)")]
        rows = conn.execute(
            f"SELECT * FROM exchange_odds WHERE updated_at >= ? AND match_id IN ({','.join('?' * len(ids))})",
            (cutoff, *ids)).fetchall()
        return {r[0]: dict(zip(cols, r)) for r in rows}
    finally:
        conn.close()


def side_exchange(row, is_home):
    """(back, back_size, lay, lay_size, updated_at) for one side, or None."""
    if not row:
        return None
    s = "home" if is_home else "away"
    if not row.get(f"{s}_lay"):
        return None
    return (row.get(f"{s}_back"), row.get(f"{s}_back_size"), row.get(f"{s}_lay"),
            row.get(f"{s}_lay_size"), row.get("updated_at"))


def refresh(hours=24, client=None, log=print):
    """Fetch and store Betfair Match Odds prices for our fixtures. Returns a summary."""
    from collectors import betfair
    from collectors.apisports import api_get
    client = client or betfair.Client()
    fixtures = our_fixtures(hours, api_get)
    markets = match_odds_markets(client, hours)
    paired = match_markets(markets, fixtures)
    books = betfair.books(client, [m["marketId"] for m in paired.values()]) if paired else {}
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    ensure_table(conn)
    saved = 0
    for mid, market in paired.items():
        book = books.get(market["marketId"])
        prices = side_prices(market, book)
        if prices:
            save(conn, mid, market, book, prices, ts)
            saved += 1
    conn.commit()
    conn.close()
    summary = {"fixtures": len(fixtures), "betfair_markets": len(markets), "matched": len(paired),
               "saved": saved, "unmatched": [f"{f['home']} v {f['away']}" for f in fixtures
                                             if str(f["match_id"]) not in paired][:15]}
    log(f"{len(fixtures)} fixtures, {len(markets)} Betfair markets, matched {len(paired)}, saved {saved}")
    if summary["unmatched"]:
        log("not found on Betfair (first 15): " + "; ".join(summary["unmatched"]))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    args = ap.parse_args()
    refresh(args.hours)


if __name__ == "__main__":
    main()
