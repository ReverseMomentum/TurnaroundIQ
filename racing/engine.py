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

from typing import Optional

import numpy as np

from racing import calibrate, confidence, kelly, market, nonfinish, positions
from racing.extra_place import Terms, evaluate, min_value_odds, parse_fraction, shrink, standard_terms

MAX_POSITIONS = 9
DEFAULT_BOOK = "Best price"


def _runner_features(runners, names):
    if not names:
        return None
    X = np.array([[(r.get("features") or {}).get(f, np.nan) for f in names] for r in runners], float)
    return X if np.isfinite(X).any() else None


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

    p_win, source, diag = market.fair_win_probs(runners)
    blend = calibration.get("blend")
    if blend and blend.get("fitted"):
        p_win = calibrate.apply_blend(p_win, _runner_features(runners, blend["features"][1:]), blend)

    disc = calibration.get("discounts") or positions.DEFAULT_DISCOUNTS
    n_cal = int(calibration.get("n_races") or 0) if calibration.get("fitted") else 0
    rtype = nonfinish.race_type(race.get("race_type"), race.get("name"))
    odds_for_dnf = [r.get("win_odds") or market.best_price(r.get("odds") or {}) or 1 / max(p, 1e-6)
                    for r, p in zip(runners, p_win)]
    dnf = nonfinish.rates_for(odds_for_dnf, rtype, calibration.get("dnf"))
    sim = positions.simulate(p_win, n_sims=n_sims, discounts=disc, seed=seed, dnf=dnf)
    harv = positions.simulate(p_win, n_sims=n_sims, discounts=[1.0], seed=seed + 1, dnf=dnf)
    P, top, top_se, top_h = sim["P"], sim["top"], sim["top_se"], harv["top"]
    offers = _offers(race, n)
    std_places, std_frac = standard_terms(n, bool(race.get("handicap")))

    def topk(arr, i, k):
        return float(arr[i, min(k, n) - 1]) if k >= 1 else 0.0

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
            "exchange_back": (r.get("exchange") or {}).get("back"),
            "value_from": {
                str(extra): min_value_odds(float(p_win[i]), topk(top, i, std_places + extra), std_frac,
                                           calibration.get("edge_shrink"))
                for extra in (0, 1, 2, 3) if std_frac and std_places + extra <= n
            },
            "exchange": r.get("exchange"),
            "offers": [],
        }
        for t in offers:
            odds = (r.get("odds") or {}).get(t.bookmaker) or row["best_win_odds"]
            if not market.implied(odds):
                continue
            ev = evaluate(float(p_win[i]), list(top[i]), float(odds), t)
            if calibration.get("edge_shrink") is not None:
                ev = shrink(ev, float(calibration["edge_shrink"]))
            raw_place = ev.get("raw_model_probability", ev["model_probability"])
            k = t.places
            p_h = topk(top_h, i, k)
            se = confidence.place_uncertainty(raw_place, p_h, topk(top_se, i, k), n_cal)
            parts = confidence.components(raw_place, p_h, topk(top_se, i, k), p_book, p_ex, n_cal)
            conf = confidence.score(parts)
            se_win = confidence.place_uncertainty(float(p_win[i]), float(p_win[i]), float(top_se[i, 0]), n_cal)
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
                "grade": confidence.grade(ev["each_way_ev"], robust_edge, conf,
                                          stakes["quarter"]["each_way_pct"], bool(n_cal)),
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
        "book_overround": diag["book_overround"],
        "standard_terms": {"places": std_places, "fraction": std_frac},
        "offers": [t.__dict__ for t in offers],
        "discounts": list(disc),
        "calibrated": bool(n_cal),
        "n_sims": sim["n_sims"],
        "runners": rows,
        "opportunities": opps,
    }
