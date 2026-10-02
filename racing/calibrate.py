"""
Calibration and scoring on past results.

fit_discounts  maximum-likelihood stage discounts lambda_1..lambda_6 for the
               discounted Plackett-Luce model, from finishing orders.
               lambda_1 != 1 corrects the win probabilities themselves
               (favourite-longshot bias left after de-vigging).
fit_blend      Benter-style second stage: conditional logit on
               log(market probability) plus standardised form features.
               Only used once enough races with features are loaded.
evaluate       Brier score, log loss and calibration error for top-k and
               extra-place outcomes. These, not winner accuracy, are what the
               model is judged on.

A race here is {"p_win": [...], "order": [runner indices, 1st first, ...],
"features": optional (n, m) array}.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from scipy.optimize import minimize

from racing import positions

N_STAGES = 6
MIN_RACES_DISCOUNTS = 200
MIN_RACES_BLEND = 500


def _race_nll(logp: np.ndarray, order: Sequence[int], lam: np.ndarray) -> float:
    left = np.ones(len(logp), dtype=bool)
    nll = 0.0
    for s, i in enumerate(order[:len(logp) - 1]):
        l = lam[min(s, len(lam) - 1)]
        w = l * logp[left]
        m = w.max()
        nll -= l * logp[i] - (m + np.log(np.exp(w - m).sum()))
        left[i] = False
    return nll


def _finishers_only(r: dict):
    """Log-strengths and order over the runners that finished (non-finishers are modelled separately)."""
    logp = np.log(np.clip(np.asarray(r["p_win"], float), 1e-9, None))
    order = list(r["order"])
    keep = sorted(set(order))
    if len(keep) == len(logp):
        return logp, order
    remap = {old: new for new, old in enumerate(keep)}
    return logp[keep], [remap[i] for i in order]


def fit_discounts(races: list[dict], n_stages: int = N_STAGES) -> dict:
    prepared = [_finishers_only(r) for r in races if len(r.get("order") or []) >= 2]
    if len(prepared) < MIN_RACES_DISCOUNTS:
        return {"discounts": list(positions.DEFAULT_DISCOUNTS), "fitted": False,
                "n_races": len(prepared), "reason": f"need {MIN_RACES_DISCOUNTS}+ races with results"}

    def f(lam):
        return sum(_race_nll(lp, o, lam) for lp, o in prepared) / len(prepared)

    x0 = np.array(positions.stage_discounts(n_stages))
    res = minimize(f, x0, method="L-BFGS-B", bounds=[(0.2, 1.6)] * n_stages)
    base = f(x0)
    return {
        "discounts": [round(float(v), 4) for v in res.x],
        "fitted": True,
        "n_races": len(prepared),
        "nll_prior": round(base, 5),
        "nll_fitted": round(float(res.fun), 5),
    }


def _standardise(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, float).copy()
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    sd[~np.isfinite(sd) | (sd == 0)] = 1.0
    Z = (X - mu) / sd
    Z[~np.isfinite(Z)] = 0.0
    return Z


def blend_matrix(p_win, features) -> np.ndarray:
    logp = np.log(np.clip(np.asarray(p_win, float), 1e-9, None))[:, None]
    if features is None:
        return logp
    with np.errstate(all="ignore"):
        Z = _standardise(np.atleast_2d(np.asarray(features, float)))
    return np.hstack([logp, Z])


def fit_blend(races: list[dict], feature_names: Sequence[str]) -> dict:
    data = [(blend_matrix(r["p_win"], r.get("features")), r["order"][0])
            for r in races if r.get("order") and r.get("features") is not None]
    if len(data) < MIN_RACES_BLEND:
        return {"fitted": False, "n_races": len(data), "reason": f"need {MIN_RACES_BLEND}+ races with features"}
    m = data[0][0].shape[1]

    def nll(beta):
        tot = 0.0
        for X, w in data:
            s = X @ beta
            mx = s.max()
            tot -= s[w] - (mx + np.log(np.exp(s - mx).sum()))
        return tot / len(data) + 1e-3 * float(beta[1:] @ beta[1:])

    x0 = np.zeros(m)
    x0[0] = 1.0
    res = minimize(nll, x0, method="L-BFGS-B")
    return {"fitted": True, "n_races": len(data), "weights": [round(float(v), 5) for v in res.x],
            "features": ["log_market_p", *feature_names],
            "nll_market_only": round(nll(x0), 5), "nll_fitted": round(float(res.fun), 5)}


def apply_blend(p_win, features, blend: Optional[dict]) -> np.ndarray:
    p = np.asarray(p_win, float)
    if not blend or not blend.get("fitted") or features is None:
        return p
    X = blend_matrix(p, features)
    beta = np.asarray(blend["weights"], float)
    if X.shape[1] != len(beta):
        return p
    s = X @ beta
    e = np.exp(s - s.max())
    return e / e.sum()


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    idx = np.minimum((p * bins).astype(int), bins - 1)
    err = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            err += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(err / len(p)) if len(p) else 0.0


def evaluate(races: list[dict], discounts=None, ks=(1, 3, 4, 5, 6),
             extra=((3, 4), (3, 5)), n_sims: int = 4000) -> dict:
    """
    Out-of-sample style scores for every runner in every race:
      top_k        P(finish in top k) vs whether it did
      extra a->b   P(finish in places a+1..b) vs whether it did
    """
    preds = {f"top{k}": [] for k in ks}
    preds.update({f"extra{a}to{b}": [] for a, b in extra})
    outs = {k: [] for k in preds}
    for r in races:
        order = list(r.get("order") or [])
        p = np.asarray(r["p_win"], float)
        n = len(p)
        if n < 2 or not order:
            continue
        sim = positions.simulate(p, n_sims=n_sims, discounts=discounts, seed=11, batches=2,
                                 dnf=r.get("dnf"))
        top = sim["top"]
        finish = np.full(n, n + 1)
        for pos, i in enumerate(order):
            finish[i] = pos + 1
        for k in ks:
            if k <= n:
                preds[f"top{k}"].extend(top[:, k - 1])
                outs[f"top{k}"].extend(finish <= k)
        for a, b in extra:
            if b <= n:
                preds[f"extra{a}to{b}"].extend(top[:, b - 1] - top[:, a - 1])
                outs[f"extra{a}to{b}"].extend((finish > a) & (finish <= b))
    report = {"n_races": len(races)}
    for key in preds:
        p = np.clip(np.asarray(preds[key], float), 1e-6, 1 - 1e-6)
        y = np.asarray(outs[key], float)
        if not len(p):
            continue
        report[key] = {
            "n": int(len(p)),
            "brier": round(float(np.mean((p - y) ** 2)), 5),
            "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 5),
            "calibration_error": round(_ece(p, y), 5),
            "mean_predicted": round(float(p.mean()), 4),
            "observed_rate": round(float(y.mean()), 4),
        }
    return report
