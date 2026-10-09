"""
Shadow tracker: every runner shown in a race with extra-place offers, recorded with
the grade and price it was given just before the off, then judged on the result and
on Betfair SP. Answers "what would each grade have returned?" without anyone placing
or logging a bet, so the grade thresholds can be checked against real races.

record_today()  price today's not-yet-started races that have bookmaker offers and
                upsert one row per runner per set of terms (the last run before the off wins)
report()        settled rows split by grade and price band, like the My bets tracker:
                return at the price graded, the model's EV, value at SP, placed vs model
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from database import get_db
from racing import store
from racing.engine import price_race
from racing.extra_place import ODDS_BANDS, band_label, odds_band, place_odds

UK = ZoneInfo("Europe/London")


def _started(race: dict, now: datetime) -> bool:
    today = now.date().isoformat()
    if (race.get("date") or today) != today:
        return (race.get("date") or today) < today
    t = race.get("time")
    return bool(t) and t <= now.strftime("%H:%M")


def record_today(conn=None, n_sims: int = 6000) -> int:
    own = conn is None
    conn = conn or get_db()
    store.ensure_tables(conn)
    now = datetime.now(UK)
    cal = store.latest_calibration(conn)
    saved = 0
    for race in store.races_on(now.date().isoformat(), conn):
        if _started(race, now) or not [t for t in race.get("terms") or [] if t.get("bookmaker") != "Best price"]:
            continue
        ids = {r["name"]: r.get("horse_id") for r in race.get("runners") or []}
        priced = price_race(race, cal, n_sims=n_sims)
        if not priced.get("runners"):
            continue
        for row in priced["runners"]:
            hid = ids.get(row["name"])
            if hid is None:
                continue
            by_terms: dict = {}
            for o in row["offers"]:
                if o["bookmaker"] == "Best price":
                    continue
                key = (o["places_paid"], round(float(o["fraction"]), 4))
                g = by_terms.setdefault(key, {"best": o, "books": []})
                g["books"].append(o["bookmaker"])
                if o["each_way_ev"] > g["best"]["each_way_ev"]:
                    g["best"] = o
            for (places, frac), g in by_terms.items():
                o = g["best"]
                conn.execute(
                    "INSERT INTO rac_shadow (race_id, horse_id, places, fraction, standard_places, bookmakers, odds, "
                    "price_source, value_from, grade, each_way_ev, p_win, p_place, field_size, race_type, recorded_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(race_id, horse_id, places, fraction) DO UPDATE SET "
                    "standard_places=excluded.standard_places, bookmakers=excluded.bookmakers, odds=excluded.odds, "
                    "price_source=excluded.price_source, value_from=excluded.value_from, grade=excluded.grade, "
                    "each_way_ev=excluded.each_way_ev, p_win=excluded.p_win, p_place=excluded.p_place, "
                    "field_size=excluded.field_size, race_type=excluded.race_type, recorded_at=excluded.recorded_at",
                    (race["race_id"], hid, places, frac, o["standard_places"], json.dumps(sorted(set(g["books"]))),
                     float(o["win_odds"]), o.get("price_source"), (row.get("offer_value_from") or {}).get(o["bookmaker"]),
                     o["grade"], float(o["each_way_ev"]), float(row["win_probability"]), float(o["model_probability"]),
                     priced.get("field_size"), priced.get("race_type"), store._now()))
                saved += 1
    conn.commit()
    if own:
        conn.close()
    return saved


def _ew_profit(result: str, odds: float, frac: float) -> float:
    """Return per £1 total each-way stake (50p win, 50p place)."""
    po = place_odds(odds, frac)
    if result == "won":
        return 0.5 * (odds - 1) + 0.5 * (po - 1)
    if result in ("placed", "extra_place"):
        return -0.5 + 0.5 * (po - 1)
    return -1.0


def rows(days: int = 60, conn=None) -> list[dict]:
    from racing import bets as racing_bets

    own = conn is None
    conn = conn or get_db()
    store.ensure_tables(conn)
    q = conn.execute(
        "SELECT s.race_id, s.horse_id, s.places, s.fraction, s.standard_places, s.odds, s.grade, s.each_way_ev, "
        "s.p_place, s.race_type, x.finish_position, x.placed_within, x.outside_within, r.date "
        "FROM rac_shadow s JOIN rac_races r ON r.id = s.race_id "
        "LEFT JOIN rac_results x ON x.race_id = s.race_id AND x.horse_id = s.horse_id "
        "WHERE r.date >= date('now', ?)", (f"-{int(days)} day",)).fetchall()
    if own:
        conn.close()
    cal = store.latest_calibration()
    cache: dict = {}
    out = []
    for (rid, hid, places, frac, std, odds, grade, ev, p_place, rtype, fin, pw, ow, _d) in q:
        res = store.ew_result(fin == 1, pw, ow, places or 0) if (fin or pw or ow) else None
        b = {"race_id": rid, "horse_id": hid, "odds": odds, "bookmaker": "", "places": places, "fraction": frac}
        snap = {"race": {"race_type": rtype}, "offer": {"standard_places": std}}
        out.append({
            "status": "settled" if res else "open", "result": res, "stake": 1.0,
            "profit": _ew_profit(res, odds, frac) if res else 0.0, "expected": ev,
            "clv": racing_bets.value_at_sp(b, snap, cal, cache) if res else None,
            "p_place": p_place or 0, "grade": grade or "?", "band": odds_band(odds),
        })
    return out


def report(days: int = 60) -> dict:
    from racing.bets import _summ

    rs = rows(days)
    band_order = {band_label(lo, hi): i for i, (lo, hi) in enumerate(ODDS_BANDS)}
    by = lambda key, order=None: {k: _summ([r for r in rs if r[key] == k])  # noqa: E731
                                  for k in sorted({r[key] for r in rs}, key=order)}
    return {"all": _summ(rs), "by_grade": by("grade"),
            "by_odds": by("band", lambda k: (band_order.get(k, 99), str(k))), "days": days}
