"""
Probability calibration (replaces the single edge shrink).

The backtest showed the raw model is too cautious on short and mid prices and
too generous on big outsiders (the favourite-longshot bias). One shrink factor
cannot fix both ends, so the win and place chances are recalibrated with
logistic regressions fitted on past races (Platt scaling with extra inputs):

  win:    P(won)            ~ logit(p_win)
  place:  P(placed in top k) ~ logit(p_top_k) + logit(p_win) + log(field size)

p_win in the place model lets the correction differ by price, which is what
the longshot problem needs. Calibrated win chances are renormalised to sum to 1
per race; calibrated top-k chances are kept non-decreasing in k.

Rows come from simulating past races exactly as the engine does (de-vigged SP,
fitted discounts, non-finish rates), so the correction learns the engine's
own errors.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from sklearn.linear_model import LogisticRegression

from racing import market, nonfinish, positions
from racing.extra_place import standard_terms

MIN_ROWS = 2000
ODDS_BANDS = ((1.0, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, 50.0), (50.0, 1e9))


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _place_X(p_place, p_win, n):
    p_place, p_win = np.asarray(p_place, float), np.asarray(p_win, float)
    return np.column_stack([logit(p_place), logit(p_win), np.full(len(p_place), np.log(n))
                            if np.ndim(n) == 0 else np.log(np.asarray(n, float))])


def build_rows(races: list[dict], calibration: Optional[dict] = None, extras=(0, 1, 2),
               n_sims: int = 2000) -> dict:
    """datasets.load_races output -> arrays for fit() and report()."""
    cal = calibration or {}
    win_p, win_y = [], []
    pl_p, pl_w, pl_n, pl_y, pl_odds = [], [], [], [], []
    for race in races:
        odds = [r["odds"] for r in race["runners"]]
        n = len(odds)
        if n < 2:
            continue
        p = market.devig_power(odds)
        dnf = nonfinish.rates_for(odds, race.get("race_type") or "flat", cal.get("dnf"))
        sim = positions.simulate(p, n_sims=n_sims, discounts=cal.get("discounts"), seed=3,
                                 batches=2, dnf=dnf)
        top = sim["top"]
        finish = [f if f else n + 1 for f in race["finish"]]
        std, _ = standard_terms(n, race.get("handicap", False))
        win_p.extend(p)
        win_y.extend(int(f == 1) for f in finish)
        for extra in extras:
            k = std + extra
            if k >= n or k < 2:
                continue
            pl_p.extend(top[:, k - 1])
            pl_w.extend(p)
            pl_n.extend([n] * n)
            pl_y.extend(int(f <= k) for f in finish)
            pl_odds.extend(odds)
    return {"win_p": np.array(win_p), "win_y": np.array(win_y),
            "place_p": np.array(pl_p), "place_win": np.array(pl_w), "place_n": np.array(pl_n),
            "place_y": np.array(pl_y), "place_odds": np.array(pl_odds)}


def fit(rows: dict) -> dict:
    if len(rows["place_y"]) < MIN_ROWS:
        return {"fitted": False, "reason": f"need {MIN_ROWS}+ runner rows"}
    w = LogisticRegression(C=1e4, max_iter=2000).fit(logit(rows["win_p"])[:, None], rows["win_y"])
    pl = LogisticRegression(C=1e4, max_iter=2000).fit(
        _place_X(rows["place_p"], rows["place_win"], rows["place_n"]), rows["place_y"])
    return {"fitted": True, "n_rows": int(len(rows["place_y"])),
            "win": [round(float(w.intercept_[0]), 5), round(float(w.coef_[0][0]), 5)],
            "place": [round(float(pl.intercept_[0]), 5), *[round(float(c), 5) for c in pl.coef_[0]]]}


def calibrate_win(p_win, recal: dict) -> np.ndarray:
    a, b = recal["win"]
    q = _sigmoid(a + b * logit(p_win))
    return q / q.sum()


def calibrate_place(p_place, p_win, n, recal: dict) -> np.ndarray:
    c = np.asarray(recal["place"], float)
    X = _place_X(p_place, p_win, n)
    return _sigmoid(c[0] + X @ c[1:])


def apply(p_win, top, recal: Optional[dict]):
    """(p_win, top matrix) -> calibrated copies. No-op without a fitted calibration."""
    if not recal or not recal.get("fitted"):
        return np.asarray(p_win, float), top
    p_win = np.asarray(p_win, float)
    n = len(p_win)
    p_c = calibrate_win(p_win, recal)
    top_c = np.empty_like(top)
    for k in range(top.shape[1]):
        top_c[:, k] = calibrate_place(top[:, k], p_win, n, recal) if k + 1 < n else top[:, k]
    top_c[:, 0] = p_c                      # top-1 is the win chance
    top_c = np.maximum.accumulate(np.clip(top_c, 0, 1), axis=1)
    return p_c, top_c


def _ece(p, y, bins=10):
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).sum()
                     for b in range(bins) if (idx == b).any()) / max(1, len(p)))


def report(rows: dict, recal: dict) -> dict:
    """Place-probability calibration, raw vs calibrated, overall and by win odds band."""
    raw = rows["place_p"]
    cal = calibrate_place(raw, rows["place_win"], rows["place_n"], recal)
    y, odds = rows["place_y"], rows["place_odds"]
    out = {}
    for label, lo, hi in [("all", 0, 1e9), *[(f"{lo:g}-{hi:g}" if hi < 1e9 else f"{lo:g}+", lo, hi)
                                            for lo, hi in ODDS_BANDS]]:
        m = (odds >= lo) & (odds < hi)
        if m.sum() < 50:
            continue
        out[label] = {"n": int(m.sum()), "actual": round(float(y[m].mean()), 4),
                      "raw": round(float(raw[m].mean()), 4), "calibrated": round(float(cal[m].mean()), 4),
                      "raw_ece": round(_ece(raw[m], y[m]), 4), "cal_ece": round(_ece(cal[m], y[m]), 4)}
    return out
