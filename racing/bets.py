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
from racing.extra_place import ODDS_BANDS, band_label, odds_band, parse_fraction

UK = ZoneInfo("Europe/London")
SNAPSHOT_RUNNER_KEYS = ("number", "draw", "jockey", "trainer", "age", "weight", "official_rating", "form",
                        "win_probability", "top3_probability", "top4_probability", "top5_probability",
                        "top6_probability", "positions", "exchange", "place_exchange", "value_from",
                        "offer_value_from")
SNAPSHOT_RACE_KEYS = ("date", "time", "course", "name", "distance", "race_class", "going", "handicap",
                      "race_type", "surface", "field_size", "standard_terms", "probability_source",
                      "book_overround", "discounts", "calibrated", "recalibrated", "n_sims")


class TrackError(ValueError):
    pass


LAY_MODES = ("none", "win", "full")


def track(app_user_id: str, race_id: int, horse: str, bookmaker: str, odds: float, stake: float,
          places: int, fraction, paper: bool = True, lay_pct: float = 0.0, lay_odds: Optional[float] = None,
          commission: Optional[float] = None, lay_mode: Optional[str] = None,
          place_lay_odds: Optional[float] = None) -> dict:
    """
    lay_mode: "none"; "win" (part lay: the win half laid on Betfair's win market);
    "full" (the win half and the place half laid, the place on Betfair's place
    market at the standard places, so the bet mainly pays on an extra place).
    lay_pct is the older form (share of the win lay) and is used when lay_mode is not given.
    """
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
    if lay_mode is None:
        lay_mode = "win" if lay_pct and lay_pct > 0 else "none"
    if lay_mode not in LAY_MODES:
        raise TrackError("lay mode must be none, win or full")
    pct = (lay_pct or 100) if lay_mode == "win" and lay_pct else 100
    lay_odds = lay_odds or (runner.get("exchange") or {}).get("lay")
    lay_stake = liability = place_lay_stake = None
    std = priced["standard_terms"]["places"]
    if lay_mode != "none":
        if not lay_odds or lay_odds <= 1:
            raise TrackError("lay odds needed for a lay (no exchange lay price for this runner)")
        lay_stake, liability = tracked_store.ew_lay_stake(stake, odds, lay_odds, commission or 0, pct)
    if lay_mode == "full":
        if not priced["standard_terms"]["fraction"] or not std:
            raise TrackError("no standard place market for this race (win only)")
        if not place_lay_odds or place_lay_odds <= 1:
            raise TrackError(f"place lay odds needed for a full lay (Betfair's place market, {std} places)")
        place_lay_stake, place_liab = tracked_store.ew_place_lay_stake(stake, odds, frac, place_lay_odds,
                                                                       commission or 0)
        liability = round((liability or 0) + place_liab, 2)
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
        "lay": {"mode": lay_mode, "pct": pct if lay_stake else 0, "odds": lay_odds if lay_stake else None,
                "stake": lay_stake, "place_odds": place_lay_odds if place_lay_stake else None,
                "place_stake": place_lay_stake, "standard_places": std, "liability": liability,
                "commission": commission},
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
        "commission": float(commission) if commission is not None and lay_stake else 0.0,
        "lay_odds": float(lay_odds) if lay_stake else None,
        "lay_stake": lay_stake,
        "liability": liability,
        "fta_pct": round(100 * offer["model_probability"], 2),
        "notes": f"each-way {int(places)} places 1/{round(1 / frac)}"
                 + (f"; win lay £{lay_stake:.2f} @ {lay_odds:g}" if lay_stake else "")
                 + (f"; place lay ({std} pl) £{place_lay_stake:.2f} @ {place_lay_odds:g}" if place_lay_stake else ""),
        "place_lay_odds": float(place_lay_odds) if place_lay_stake else None,
        "place_lay_stake": place_lay_stake,
        "std_places": std,
        "p_std": _top(row, std),
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


def _top(row: dict, k: int) -> Optional[float]:
    """Model chance of finishing in the first k (top3-6 recalibrated, else summed positions)."""
    if not k:
        return None
    v = row.get(f"top{k}_probability")
    return float(v) if v is not None else float(sum((row.get("positions") or [])[:k]))


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
        lay = (b["snapshot"] or {}).get("lay") or {}
        if result == "placed" and lay.get("place_stake"):
            # full lay: inside the standard places (place lay loses) or only an extra place (it wins)?
            inside = store.ew_result(False, b["placed_within"], b["outside_within"], lay.get("standard_places") or 0)
            result = {"placed": "placed", "lost": "extra_place"}.get(inside)    # None: wait for a manual result
        if result:
            tracked_store.settle_tracked(b["app_user_id"], b["tracked_bet_id"], result)
            n += 1
    return n


def _band(odds: float) -> str:
    return odds_band(odds)


def _summ(rows: list[dict]) -> dict:
    settled = [r for r in rows if r["status"] == "settled" and r["result"] != "void"]
    staked = sum(r["stake"] for r in settled)
    profit = sum(r["profit"] for r in settled)
    expected = sum(r["expected"] or 0 for r in settled)
    clv = [r["clv"] for r in rows if r["clv"] is not None]
    placed = [r for r in settled if r["result"] in ("won", "placed", "extra_place", "lost")]
    return {
        "bets": len(rows), "settled": len(settled),
        "staked": round(staked, 2), "profit": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else None,
        "expected_roi": round(expected / staked, 4) if staked else None,
        "avg_clv": round(sum(clv) / len(clv), 4) if clv else None,
        "beat_sp": round(sum(c > 0 for c in clv) / len(clv), 3) if clv else None,
        "placed_rate": round(sum(r["result"] in ("won", "placed", "extra_place") for r in placed) / len(placed), 3)
        if placed else None,
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
    band_order = {band_label(lo, hi): i for i, (lo, hi) in enumerate(ODDS_BANDS)}
    order = lambda k: (band_order.get(k, 99), str(k))  # noqa: E731  odds brackets in price order
    split = lambda key: {k: _summ([r for r in rows if r[key] == k])  # noqa: E731
                         for k in sorted({r[key] for r in rows}, key=order)}
    return {"all": _summ(rows), "by_grade": split("grade"), "by_odds": split("band"),
            "by_race_type": split("race_type"), "by_bookmaker": split("bookmaker"), "by_places": split("places")}
