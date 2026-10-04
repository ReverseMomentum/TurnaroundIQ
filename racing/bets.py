"""
Tracked racing bets: snapshot, settle, report.

track()       Prices the race again with the bettor's own bookmaker, odds and
              each-way terms, then stores the bet in My bets (tracked_bets,
              product "stables") plus a snapshot of everything the model knew
              at that moment (rac_bets): chances, value line, grade, exchange
              price, race and runner details, model settings.
auto_settle() Settles open racing bets from Betfair results (won / placed /
              unplaced, void for non-runners). Bets whose paid places go deeper
              than Betfair's place markets wait for a manual result.
report()      What the snapshots say vs what happened: return against the
              model's expected return, closing-line value (odds taken vs Betfair
              SP), and the same split by grade, price, race type, bookmaker and
              places. This is the data for the next model refit.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from api import tracked as tracked_store
from database import get_db
from racing import store
from racing.engine import price_race
from racing.extra_place import parse_fraction

UK = ZoneInfo("Europe/London")
SNAPSHOT_RUNNER_KEYS = ("number", "draw", "jockey", "trainer", "age", "weight", "official_rating", "form",
                        "win_probability", "top3_probability", "top4_probability", "top5_probability",
                        "top6_probability", "positions", "exchange", "value_from", "offer_value_from")
SNAPSHOT_RACE_KEYS = ("date", "time", "course", "name", "distance", "race_class", "going", "handicap",
                      "race_type", "surface", "field_size", "standard_terms", "probability_source",
                      "book_overround", "discounts", "calibrated", "recalibrated", "n_sims")


class TrackError(ValueError):
    pass


def track(app_user_id: str, race_id: int, horse: str, bookmaker: str, odds: float, stake: float,
          places: int, fraction, paper: bool = True) -> dict:
    frac = parse_fraction(fraction)
    if not frac or frac > 1:
        raise TrackError("fraction must look like 1/5")
    if not odds or odds <= 1:
        raise TrackError("odds must be above evens-1 (decimal > 1)")
    conn = get_db()
    try:
        race = store.load_race(conn, race_id)
    finally:
        conn.close()
    if not race:
        raise TrackError("race not found")
    runner = next((r for r in race["runners"] if r["name"] == horse), None)
    if runner is None:
        raise TrackError("runner not found in that race")
    if runner.get("non_runner"):
        raise TrackError("that horse is a non-runner")
    book = (bookmaker or "Bookmaker").strip()[:40]
    runner["odds"] = {**(runner.get("odds") or {}), book: float(odds)}
    race["terms"] = [*(t for t in race.get("terms") or [] if t["bookmaker"] != book),
                     {"bookmaker": book, "places": int(places), "fraction": frac}]
    cal = store.latest_calibration()
    priced = price_race(race, cal)
    row = next(r for r in priced["runners"] if r["name"] == horse)
    offer = next((o for o in row["offers"] if o["bookmaker"] == book), None)
    if offer is None:
        raise TrackError("could not price this bet")
    now = datetime.now(UK)
    off = f"{race.get('date')} {race.get('time') or '00:00'}"
    try:
        mins_to_off = round((datetime.strptime(off, "%Y-%m-%d %H:%M").replace(tzinfo=UK) - now).total_seconds() / 60)
    except ValueError:
        mins_to_off = None
    snapshot = {
        "race": {k: priced.get(k) for k in SNAPSHOT_RACE_KEYS},
        "runner": {k: row.get(k) for k in SNAPSHOT_RUNNER_KEYS},
        "offer": {k: offer.get(k) for k in ("places_paid", "standard_places", "fraction", "win_odds", "place_odds",
                                            "model_probability", "raw_model_probability", "market_probability",
                                            "edge", "extra_place_probability", "win_ev", "place_ev",
                                            "each_way_ev", "uncertainty", "robust_edge", "confidence",
                                            "confidence_parts", "grade", "recommended_stake_pct")},
        "value_from": row["offer_value_from"].get(book),
        "minutes_to_off": mins_to_off,
        "calibration": {k: cal.get(k) for k in ("fitted", "n_races", "created_at", "source")},
        "paper": bool(paper),
    }
    bet = tracked_store.create_tracked(app_user_id, {
        "home_team": horse,
        "away_team": f"{race.get('time') or ''} {race.get('course') or ''}".strip(),
        "team": horse,
        "league": f"Racing · {book} {int(places)} pl 1/{round(1 / frac)}",
        "kickoff": f"{race.get('date')}T{race.get('time') or '00:00'}",
        "bookmaker": book,
        "back_odds": float(odds),
        "stake": float(stake),
        "commission": 0.0,
        "fta_pct": round(100 * offer["model_probability"], 2),
        "notes": f"each-way {int(places)} places 1/{round(1 / frac)}",
        "paper": bool(paper),
        "product": "stables",
        "ew_places": int(places),
        "ew_fraction": frac,
        "p_win": row["win_probability"],
        "p_place": offer["model_probability"],
    })
    store.record_bet(bet["id"], app_user_id, race_id, runner.get("horse_id"), horse, book, float(odds),
                     int(places), frac, snapshot)
    return {**bet, "snapshot": snapshot}


def _open_ids() -> set:
    conn = get_db()
    try:
        tracked_store.ensure_tracked_tables()
        return {r[0] for r in conn.execute(
            "SELECT id FROM tracked_bets WHERE status = 'open' AND product = 'stables'")}
    finally:
        conn.close()


def _non_runner(race_id: int, horse_id) -> bool:
    if horse_id is None:
        return False
    conn = get_db()
    try:
        row = conn.execute("SELECT non_runner FROM rac_runners WHERE race_id = ? AND horse_id = ?",
                           (race_id, horse_id)).fetchone()
        return bool(row and row[0])
    finally:
        conn.close()


def auto_settle() -> int:
    open_ids = _open_ids()
    n = 0
    for b in store.bets_with_results():
        if b["tracked_bet_id"] not in open_ids:
            continue
        result = "void" if _non_runner(b["race_id"], b["horse_id"]) else b["ew_result"]
        if result:
            tracked_store.settle_tracked(b["app_user_id"], b["tracked_bet_id"], result)
            n += 1
    return n


def _band(odds: float) -> str:
    for hi, label in ((5, "1-5"), (10, "5-10"), (20, "10-20"), (51, "20-50")):
        if odds < hi:
            return label
    return "50+"


def _summ(rows: list[dict]) -> dict:
    settled = [r for r in rows if r["status"] == "settled" and r["result"] != "void"]
    staked = sum(r["stake"] for r in settled)
    profit = sum(r["profit"] for r in settled)
    expected = sum(r["expected"] or 0 for r in settled)
    clv = [r["clv"] for r in rows if r["clv"] is not None]
    placed = [r for r in settled if r["result"] in ("won", "placed", "lost")]
    return {
        "bets": len(rows), "settled": len(settled),
        "staked": round(staked, 2), "profit": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else None,
        "expected_roi": round(expected / staked, 4) if staked else None,
        "avg_clv": round(sum(clv) / len(clv), 4) if clv else None,
        "beat_sp": round(sum(c > 0 for c in clv) / len(clv), 3) if clv else None,
        "placed_rate": round(sum(r["result"] in ("won", "placed") for r in placed) / len(placed), 3) if placed else None,
        "model_place": round(sum(r["p_place"] for r in placed) / len(placed), 3) if placed else None,
    }


def report(app_user_id: str, paper: Optional[bool] = None) -> dict:
    tracked = {b["id"]: b for b in tracked_store.list_tracked(app_user_id, limit=5000) if b["product"] == "stables"}
    rows = []
    for b in store.bets_with_results(app_user_id):
        t = tracked.get(b["tracked_bet_id"])
        if t is None or (paper is not None and t["paper"] != paper):
            continue
        snap = b["snapshot"]
        offer = snap.get("offer") or {}
        rows.append({
            "status": t["status"], "result": t["result"], "stake": float(t["stake"] or 0),
            "profit": float(t["actual_profit"] or 0), "expected": t["expected_profit"],
            "odds": b["odds"], "bsp": b["bsp"],
            "clv": (b["odds"] / b["bsp"] - 1) if b["bsp"] else None,
            "p_place": offer.get("model_probability") or 0,
            "grade": offer.get("grade") or "?", "band": _band(b["odds"]),
            "race_type": (snap.get("race") or {}).get("race_type") or "flat",
            "bookmaker": b["bookmaker"], "places": f"{b['places']} places",
        })
    split = lambda key: {k: _summ([r for r in rows if r[key] == k])  # noqa: E731
                         for k in sorted({r[key] for r in rows})}
    return {"all": _summ(rows), "by_grade": split("grade"), "by_odds": split("band"),
            "by_race_type": split("race_type"), "by_bookmaker": split("bookmaker"), "by_places": split("places")}
