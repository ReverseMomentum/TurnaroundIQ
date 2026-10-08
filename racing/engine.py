"""
Price one race end to end: prices -> win probabilities -> P1..PN ->
each-way offers -> edge, EV, confidence, stake, grade.

Input race dict:
  runners  [{name, win_odds | odds {bookmaker: price}, exchange {back, lay, volume},
             non_runner, features {...}, draw, jockey, trainer, ...}]
  terms    [{bookmaker, places, fraction}]   extra-place offers; optional
  handicap bool (sets standard each-way terms), plus any race labels
Optional: calibration {"discounts": [...], "n_races": int, "blend": {...}}
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from racing import calibrate, confidence, kelly, learn, market, nonfinish, positions, recalibrate
from racing.extra_place import Terms, evaluate, min_value_odds, parse_fraction, shrink, standard_terms

MAX_POSITIONS = 9
# Backtests 2018-20: at 50/1+ the model's EV was far above what came in (+12% vs
# -4% at one extra place), and with the learned model and field-size curves the
# 33/1-50/1 band did the same (model +18% vs +1%, also +7% vs -3% before), while
# shorter bands were close. Runners at 33/1 (decimal 34) or bigger get no value
# call: no grade above C, no "value from" price.
MAX_VALUE_ODDS = 34.0
DEFAULT_BOOK = "Best price"


def _runner_features(runners, names):
    if not names:
        return None
    X = np.array([[(r.get("features") or {}).get(f, np.nan) for f in names] for r in runners], float)
    return X if np.isfinite(X).any() else None


SHOWN_FEATURES = ("last_pos", "avg3_pos", "avg5_pos", "log_days", "course_rate", "distance_rate",
                  "jockey_rate", "trainer_rate", "jockey_30d", "trainer_30d", "horse_jockey_rate",
                  "or_rel", "or_gap_top", "or_missing", "history_runs", "place_excess", "win_excess",
                  "priced_runs", "course_runs", "distance_runs", "horse_jockey_runs", "jockey_runs",
                  "trainer_runs", "jockey_30d_runs", "trainer_30d_runs")


def opportunity_score(edge: float, confidence: int, volume, field_size: int) -> float:
    """
    Edge x Confidence x Liquidity x Field size, 0-100ish. Edge in points; liquidity
    from exchange matched volume (GBP 10k+ = full marks, unknown = half); field
    size saturates at 16 runners (bigger fields pay more extra places).
    """
    if edge <= 0:
        return 0.0
    liquidity = min(1.0, math.log10(1 + float(volume)) / 4) if volume else 0.5
    return round(100 * edge * (confidence / 100) * liquidity * min(1.0, field_size / 16) * 10, 1)


def _within_range(price):
    return price if price is not None and price < MAX_VALUE_ODDS else None


def _cap_grade(grade: str, odds: float, thin: bool = False) -> str:
    """No A/B at 33/1+ (overrated in backtests) or while the Betfair market is not formed."""
    return "C" if (odds >= MAX_VALUE_ODDS or thin) and grade in ("A", "B") else grade


def _offers(race: dict, field_size: int) -> list[Terms]:
    std_places, std_frac = standard_terms(field_size, bool(race.get("handicap")))
    offers = []
    for t in race.get("terms") or []:
        places = int(t.get("places") or 0)
        frac = parse_fraction(t.get("fraction")) or std_frac
        if places >= 1 and frac:
            offers.append(Terms(str(t.get("bookmaker") or DEFAULT_BOOK), places, frac, std_places))
    if not offers and std_frac:
        offers.append(Terms(DEFAULT_BOOK, std_places, std_frac, std_places))
    return offers


def price_race(race: dict, calibration: Optional[dict] = None, n_sims: int = positions.N_SIMS,
               seed: int = 7) -> dict:
    calibration = calibration or {}
    runners = [r for r in race.get("runners") or [] if not r.get("non_runner")]
    n = len(runners)
    out = {k: race.get(k) for k in ("race_id", "date", "time", "course", "name", "distance",
                                    "race_class", "going", "handicap", "race_type", "surface")}
    out["field_size"] = n
    if n < 2:
        return {**out, "runners": [], "opportunities": [], "error": "need at least 2 runners"}

    # Offers with a minimum field ("12+ runners") only stand once the field is big enough.
    all_terms = race.get("terms") or []
    race = {**race, "terms": [t for t in all_terms if n >= int(t.get("min_runners") or 0)]}
    inactive = [t for t in all_terms if n < int(t.get("min_runners") or 0)]

    p_win, source, diag = market.fair_win_probs(runners)
    # Betfair market not formed yet (wide back/lay gaps): chances are shaky, so no A/B grades
    market_thin = source in ("exchange", "partial") and diag["formed_share"] < market.FORMED_SHARE
    # what a bookmaker would likely offer (exchange fair chances + a typical book), for races with no bookmaker prices
    est_book = market.estimated_book_odds(p_win, calibration.get("book_overround"))
    blend = calibration.get("blend")
    if blend and blend.get("fitted") and blend.get("kind") == "exploded":
        p_win = learn.apply(p_win, runners, blend)          # learned ranking model (racing/learn.py)
    elif blend and blend.get("fitted"):
        p_win = calibrate.apply_blend(p_win, _runner_features(runners, blend["features"][1:]), blend)

    n_cal = int(calibration.get("n_races") or 0) if calibration.get("fitted") else 0
    rtype = nonfinish.race_type(race.get("race_type"), race.get("name"))
    disc = calibrate.discounts_for(calibration, rtype, n)   # race type / field size curve when fitted
    odds_for_dnf = [r.get("win_odds") or market.best_price(r.get("odds") or {}) or 1 / max(p, 1e-6)
                    for r, p in zip(runners, p_win)]
    dnf = nonfinish.rates_for(odds_for_dnf, rtype, calibration.get("dnf"))
    sim = positions.simulate(p_win, n_sims=n_sims, discounts=disc, seed=seed, dnf=dnf)
    harv = positions.simulate(p_win, n_sims=n_sims, discounts=[1.0], seed=seed + 1, dnf=dnf)
    P, top_raw, top_se, top_h = sim["P"], sim["top"], sim["top_se"], harv["top"]
    recal = calibration.get("recal")
    p_raw = p_win
    p_win, top = recalibrate.apply(p_raw, top_raw, recal)
    # The fitted calibration replaces the older single edge shrink.
    edge_shrink = None if (recal and recal.get("fitted")) else calibration.get("edge_shrink")
    offers = _offers(race, n)
    std_places, std_frac = standard_terms(n, bool(race.get("handicap")))

    def topk(arr, i, k):
        return float(arr[i, min(k, n) - 1]) if k >= 1 else 0.0

    ref_price = [r.get("win_odds") or market.best_price(r.get("odds") or {})
                 or (r.get("exchange") or {}).get("back") or 1.0 / max(float(p), 1e-6)
                 for r, p in zip(runners, p_raw)]
    rows, opps = [], []
    for i, r in enumerate(runners):
        p_book = diag["p_book"][i] if diag["p_book"] is not None else None
        p_ex = diag["p_exchange"][i] if diag["p_exchange"] is not None else None
        row = {
            "name": r.get("name") or r.get("horse") or f"Runner {i + 1}",
            **{k: r.get(k) for k in ("number", "draw", "jockey", "trainer", "age", "weight",
                                     "official_rating", "form")},
            "win_probability": float(p_win[i]),
            **{f"top{k}_probability": topk(top, i, k) for k in (3, 4, 5, 6)},
            "positions": [round(float(x), 5) for x in P[i, :MAX_POSITIONS]],
            "best_win_odds": r.get("win_odds") or market.best_price(r.get("odds") or {}),
            "est_book_odds": est_book[i],
            "market_formed": bool(diag["formed"][i]),
            "exchange_back": (r.get("exchange") or {}).get("back"),
            "value_from": {} if ref_price[i] >= MAX_VALUE_ODDS else {
                str(extra): _within_range(min_value_odds(float(p_win[i]), topk(top, i, std_places + extra),
                                                         std_frac, edge_shrink))
                for extra in (0, 1, 2, 3) if std_frac and std_places + extra <= n
            },
            "beyond_value_range": ref_price[i] >= MAX_VALUE_ODDS,
            # "Value from" on each bookmaker's own extra-place terms (race["terms"])
            "offer_value_from": {} if ref_price[i] >= MAX_VALUE_ODDS else {
                str(t.get("bookmaker")): _within_range(min_value_odds(
                    float(p_win[i]), topk(top, i, int(t.get("places") or 0)),
                    parse_fraction(t.get("fraction")) or std_frac, edge_shrink))
                for t in race.get("terms") or [] if int(t.get("places") or 0) >= 1
            },
            "exchange": r.get("exchange"),
            "place_exchange": r.get("place_exchange"),     # Betfair place markets {places: {back, lay}}
            "days_since_run": r.get("days_since_run"),
            "features": {k: v for k, v in (r.get("features") or {}).items() if k in SHOWN_FEATURES},
            "offers": [],
        }
        for t in offers:
            odds = (r.get("odds") or {}).get(t.bookmaker) or row["best_win_odds"]
            price_source = "bookmaker"
            if not market.implied(odds):
                # No bookmaker price: grade at an estimated bookmaker price, NOT the exchange price
                # (the exchange is bigger and has no each-way), until the bettor enters their own.
                odds, price_source = est_book[i], "estimated"
            if not market.implied(odds):
                continue
            ev = evaluate(float(p_win[i]), list(top[i]), float(odds), t)
            ev["price_source"] = price_source
            k = t.places
            if edge_shrink is not None:
                ev = shrink(ev, float(edge_shrink))
            elif top is not top_raw:
                ev["raw_model_probability"] = topk(top_raw, i, k)
            raw_place = ev.get("raw_model_probability", ev["model_probability"])
            p_h = topk(top_h, i, k)
            se = confidence.place_uncertainty(raw_place, p_h, topk(top_se, i, k), n_cal)
            parts = confidence.components(raw_place, p_h, topk(top_se, i, k), p_book, p_ex, n_cal)
            conf = confidence.score(parts)
            se_win = confidence.place_uncertainty(float(p_raw[i]), float(p_raw[i]), float(top_se[i, 0]), n_cal)
            robust_edge = ev["edge"] - se
            stakes = kelly.robust_stakes(float(p_win[i]), ev["model_probability"], se_win, se,
                                         float(odds), ev["place_odds"])
            ev.update({
                "uncertainty": se,
                "robust_edge": robust_edge,
                "confidence": conf,
                "confidence_label": confidence.label(conf),
                "confidence_parts": parts,
                "stakes": stakes,
                "recommended_stake_pct": stakes["quarter"]["each_way_pct"],
                "opportunity_score": opportunity_score(ev["edge"], conf, (r.get("exchange") or {}).get("volume"), n),
                "grade": _cap_grade(confidence.grade(ev["each_way_ev"], robust_edge, conf,
                                                     stakes["quarter"]["each_way_pct"], bool(n_cal)),
                                    float(odds), market_thin or not diag["formed"][i]),
            })
            row["offers"].append(ev)
            # An each-way bet includes the win part, so that is what must pay.
            if ev["edge"] > 0 and ev["each_way_ev"] > 0:
                opps.append({
                    "horse": row["name"],
                    "win_probability": row["win_probability"],
                    **{f"top{k}_probability": row[f"top{k}_probability"] for k in (3, 4, 5, 6)},
                    "p4": row["positions"][3] if n > 3 else 0.0,
                    "p5": row["positions"][4] if n > 4 else 0.0,
                    "p6": row["positions"][5] if n > 5 else 0.0,
                    **ev,
                })
        rows.append(row)

    rows.sort(key=lambda x: -x["win_probability"])
    opps.sort(key=lambda o: (o["grade"], -o["each_way_ev"]))
    return {
        **out,
        "probability_source": source,
        "market_thin": bool(market_thin),
        "market_formed_share": round(float(diag["formed_share"]), 2),
        "book_overround": diag["book_overround"],
        "standard_terms": {"places": std_places, "fraction": std_frac},
        "offers": [t.__dict__ for t in offers],
        "inactive_offers": [{k: t.get(k) for k in ("bookmaker", "places", "fraction", "min_runners")}
                            for t in inactive],
        "discounts": list(disc),
        "position_segment": calibrate.segment(rtype, n)
        if calibrate.segment(rtype, n) in (calibration.get("segment_discounts") or {}) else None,
        "calibrated": bool(n_cal),
        "recalibrated": bool(recal and recal.get("fitted")),
        "n_sims": sim["n_sims"],
        "runners": rows,
        "opportunities": opps,
    }
