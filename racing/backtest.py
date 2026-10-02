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


def to_calibration_races(races: list[dict]) -> list[dict]:
    """datasets.load_races output -> calibrate.py input (SP de-vigged)."""
    from racing import market

    return [{"p_win": market.devig_power([r["odds"] for r in race["runners"]]), "order": race["order"]}
            for race in races]


def ew_backtest(races: list[dict], calibration: Optional[dict] = None, extra: int = 1,
                min_runners: int = 8, n_sims: int = 2000, grades=("A", "B")) -> dict:
    stats = defaultdict(lambda: {"bets": 0, "staked": 0.0, "returned": 0.0, "placed": 0,
                                 "extra_place_hits": 0, "ev_sum": 0.0})
    n_races = 0
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
            "runners": [{"name": f"{i}", "win_odds": r["odds"]} for i, r in enumerate(race["runners"])],
            "terms": [{"bookmaker": "SP", "places": std_places + extra, "fraction": frac}],
        }, calibration, n_sims=n_sims, seed=zlib.crc32(race["key"].encode()))
        for o in priced["opportunities"]:
            g = o["grade"] if o["grade"] in grades else "other"
            pos = race["finish"][int(o["horse"])]
            s = stats[g]
            s["bets"] += 1
            s["staked"] += 1.0
            s["ev_sum"] += o["each_way_ev"]
            ret = 0.0
            if pos == 1:
                ret += 0.5 * o["win_odds"]
            if pos and pos <= o["places_paid"]:
                ret += 0.5 * o["place_odds"]
                s["placed"] += 1
                if pos > std_places:
                    s["extra_place_hits"] += 1
            s["returned"] += ret
    report = {"races": n_races, "extra_places": extra}
    for g, s in sorted(stats.items()):
        report[g] = {**{k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()},
                     "roi": round((s["returned"] - s["staked"]) / s["staked"], 4) if s["staked"] else None,
                     "mean_model_ev": round(s["ev_sum"] / s["bets"], 4) if s["bets"] else None}
    return report


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
