"""
Free checks of the model on past races.

ew_backtest   Paper each-way bets on held-back races. Each race gets a
              hypothetical extra-place offer (standard places + N at the
              standard fraction) priced at SP; the runners the engine grades
              are backed 1 unit each-way and settled on the real finishing order.
              SP carries more margin than early prices, and dead-heat and Rule 4
              deductions are ignored, so this checks the direction of the edge,
              not a return anyone would have got.

bsp_check     Betfair BSP files: the win market's BSP gives win probabilities,
              the "To Be Placed" market shows who placed and how many places it
              paid (2-5). Scores the model's P(top k) against what happened,
              next to the place market's own BSP as a benchmark.
"""

from __future__ import annotations

import csv
import io
import zlib
from collections import defaultdict
from typing import Optional

import numpy as np

from racing import calibrate, positions
from racing.engine import price_race
from racing.extra_place import standard_terms


def to_calibration_races(races: list[dict], dnf_table: Optional[dict] = None,
                         blend: Optional[dict] = None) -> list[dict]:
    """
    datasets.load_races output -> calibrate.py input (SP de-vigged). With a
    non-finisher table, each race also carries per-runner non-finish rates.
    """
    from racing import learn, market, nonfinish

    out = []
    for race in races:
        odds = [r["odds"] for r in race["runners"]]
        row = {"p_win": learn.apply(market.devig_power(odds), race["runners"], blend), "order": race["order"]}
        if dnf_table is not None:
            row["dnf"] = nonfinish.rates_for(odds, race.get("race_type") or "flat", dnf_table)
        out.append(row)
    return out


def ew_bets(races: list[dict], calibration: Optional[dict] = None, extra: int = 1,
            min_runners: int = 8, n_sims: int = 2000) -> tuple[int, list[dict]]:
    """
    Price each race with a hypothetical offer (standard places + extra, standard
    fraction, at SP) and settle 1 unit each-way on every runner the engine shows
    as an opportunity. Returns (races used, one record per bet).
    """
    bets, n_races = [], 0
    for race in races:
        n = len(race["runners"])
        if n < min_runners:
            continue
        std_places, frac = standard_terms(n, race["handicap"])
        if not frac:
            continue
        n_races += 1
        priced = price_race({
            "handicap": race["handicap"],
            "race_type": race.get("race_type"),
            "runners": [{"name": f"{i}", "win_odds": r["odds"], "features": r.get("features")}
                        for i, r in enumerate(race["runners"])],
            "terms": [{"bookmaker": "SP", "places": std_places + extra, "fraction": frac}],
        }, calibration, n_sims=n_sims, seed=zlib.crc32(race["key"].encode()))
        for o in priced["opportunities"]:
            pos = race["finish"][int(o["horse"])]
            ret = (0.5 * o["win_odds"] if pos == 1 else 0.0)
            placed = bool(pos and pos <= o["places_paid"])
            if placed:
                ret += 0.5 * o["place_odds"]
            bets.append({
                "grade": o["grade"], "ev": o["each_way_ev"], "win_ev": o["win_ev"],
                "p_place": o.get("raw_model_probability", o["model_probability"]),
                "market_place": o["market_probability"], "place_odds": o["place_odds"],
                "win_odds": o["win_odds"], "return": ret, "placed": placed,
                "extra_hit": placed and pos > std_places, "race_type": race.get("race_type") or "flat",
            })
    return n_races, bets


def _summ(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"bets": 0}
    ret = sum(b["return"] for b in rows)
    return {"bets": n, "model_ev": round(sum(b["ev"] for b in rows) / n, 4),
            "roi": round(ret / n - 1, 4), "placed": sum(b["placed"] for b in rows),
            "extra_place_hits": sum(b["extra_hit"] for b in rows)}


EV_BANDS = ((0.0, 0.04), (0.04, 0.10), (0.10, 0.20), (0.20, 9.0))
from racing.extra_place import ODDS_BANDS, band_label  # noqa: E402


def summarise(bets: list[dict]) -> dict:
    """Model EV vs actual ROI by grade, by model-EV band, by price band and race type."""
    out = {"all": _summ(bets),
           "by_grade": {g: _summ([b for b in bets if b["grade"] == g]) for g in "ABC"},
           "by_ev": {f"{lo:+.0%} to {hi:+.0%}" if hi < 9 else f"{lo:+.0%}+":
                     _summ([b for b in bets if lo <= b["ev"] < hi]) for lo, hi in EV_BANDS},
           "by_odds": {band_label(lo, hi):
                       _summ([b for b in bets if lo <= b["win_odds"] < hi]) for lo, hi in ODDS_BANDS},
           "by_type": {t: _summ([b for b in bets if b["race_type"] == t]) for t in ("flat", "hurdle", "chase")}}
    return out


def adjusted_ev(b: dict, w: float) -> float:
    adj = min(1.0, max(0.0, b["market_place"] + w * (b["p_place"] - b["market_place"])))
    return 0.5 * (b["win_ev"] + adj * b["place_odds"] - 1.0)


def fit_shrink(bets: list[dict], min_ev: float = 0.04, min_bets: int = 300) -> dict:
    """
    Pick w (0..1) so that, among bets whose shrunk EV is still >= min_ev (the
    ones the page would show as value), the mean shrunk EV matches the actual
    ROI. Fit on training races only, then checked on the test races.
    """
    best = None
    for w in [i / 20 for i in range(21)]:
        sel = [(adjusted_ev(b, w), b["return"] - 1) for b in bets]
        sel = [x for x in sel if x[0] >= min_ev]
        if len(sel) < min_bets:
            continue
        gap = abs(sum(e for e, _ in sel) / len(sel) - sum(r for _, r in sel) / len(sel))
        if best is None or gap < best[1] - 1e-9 or (abs(gap - best[1]) < 0.002 and w > best[0]):
            best = (w, gap, len(sel))
    if best is None:
        return {"edge_shrink": 1.0, "fitted": False, "reason": f"fewer than {min_bets} bets"}
    return {"edge_shrink": best[0], "fitted": True, "gap": round(best[1], 4), "bets": best[2]}


def ew_backtest(races: list[dict], calibration: Optional[dict] = None, extra: int = 1,
                min_runners: int = 8, n_sims: int = 2000) -> dict:
    n_races, bets = ew_bets(races, calibration, extra, min_runners, n_sims)
    return {"races": n_races, "extra_places": extra, **summarise(bets)}


# ---- Betfair BSP files ------------------------------------------------------

def _rows(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return [{(k or "").strip().upper(): (v or "").strip() for k, v in row.items()} for row in reader]


def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 1 else None


def bsp_races(win_text: str, place_text: str) -> list[dict]:
    """Join one day's win and place files into races with BSPs and placed flags."""
    win = defaultdict(dict)
    for r in _rows(win_text):
        win[(r.get("MENU_HINT"), r.get("EVENT_DT"))][r.get("SELECTION_ID")] = r
    place = defaultdict(dict)
    for r in _rows(place_text):
        place[(r.get("MENU_HINT"), r.get("EVENT_DT"))][r.get("SELECTION_ID")] = r
    out = []
    for key, runners in win.items():
        pl = place.get(key)
        if not pl:
            continue
        ids = [s for s in runners if _f(runners[s].get("BSP")) and s in pl]
        if len(ids) < 4 or len(ids) != len(runners):
            continue
        placed = [1 if pl[s].get("WIN_LOSE") in ("1", "2") else 0 for s in ids]
        k = sum(placed)
        if k < 1 or k >= len(ids):
            continue
        bsp = np.array([_f(runners[s]["BSP"]) for s in ids])
        p = (1 / bsp) / (1 / bsp).sum()
        pbsp = [_f(pl[s].get("BSP")) for s in ids]
        out.append({"key": f"{key[0]}|{key[1]}", "p_win": p, "placed": placed, "places": k,
                    "place_bsp": pbsp, "won": [1 if runners[s].get("WIN_LOSE") == "1" else 0 for s in ids]})
    return out


def _score(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return {"n": int(len(p)),
            "brier": round(float(np.mean((p - y) ** 2)), 5),
            "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 5),
            "calibration_error": round(calibrate._ece(p, y), 5),
            "mean_predicted": round(float(p.mean()), 4),
            "observed_rate": round(float(y.mean()), 4)}


def bsp_check(races: list[dict], discount_sets: dict, n_sims: int = 2000) -> dict:
    """
    discount_sets: {"label": discounts}. For each places-paid value k, scores
    every model's P(top k) and the place market's own BSP on the same runners.
    """
    by_k = defaultdict(lambda: defaultdict(lambda: ([], [])))
    for race in races:
        k = race["places"]
        bucket = by_k[k]
        ok = [i for i, b in enumerate(race["place_bsp"]) if b]
        for label, disc in discount_sets.items():
            top = positions.simulate(race["p_win"], n_sims=n_sims, discounts=disc, seed=5,
                                     batches=2)["top"]
            col = top[:, min(k, len(race["p_win"])) - 1]
            bucket[label][0].extend(col[ok])
            bucket[label][1].extend(np.asarray(race["placed"])[ok])
        bucket["place_market_bsp"][0].extend(1 / np.asarray([race["place_bsp"][i] for i in ok]))
        bucket["place_market_bsp"][1].extend(np.asarray(race["placed"])[ok])
    report = {}
    for k in sorted(by_k):
        report[f"top{k}"] = {label: _score(p, y) for label, (p, y) in by_k[k].items() if len(p)}
    return report
