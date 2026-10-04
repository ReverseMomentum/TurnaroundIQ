"""
Learned runner strengths: a ranking model on top of the market.

Each runner's strength is
    u = a * log(market probability) + sum_k beta_k * z_k
where z are the standardised features (racing/features.py; missing = average).
The finishing order is modelled as discounted Plackett-Luce, the same model the
engine simulates: at stage s the next finisher is drawn from those left with
weight exp(lambda_s * u). Fitting maximises the likelihood of the first six
finishers ("exploded logit"), so the features are learned on 2nd-6th as well
as the winner, which is where extra-place value sits. Non-finishers are left
out of the candidate sets (they are modelled separately). A race tagged with
its own "discounts" (race type / field size) uses those.

Feature groups are added one at a time and kept only if they lower the
held-back (validation) loss, like the FTA model's input selection.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from scipy.optimize import minimize

from racing import features as F
from racing import market, positions

MAX_RUNNERS = 24
STAGES = 6
L2 = 1e-3
MIN_GAIN = 2e-4      # validation loss must fall by at least this to keep a group


def _arrays(races: list[dict], names: Sequence[str], discounts, stats: Optional[dict] = None):
    """Pad races into arrays: logp (R,N), X (R,N,F), finisher mask (R,N), order (R,S)."""
    R, N, Fn = len(races), MAX_RUNNERS, len(names)
    logp = np.zeros((R, N))
    X = np.zeros((R, N, Fn))
    ok = np.zeros((R, N), bool)
    order = -np.ones((R, STAGES), int)
    raw = np.full((R, N, Fn), np.nan)
    for r, race in enumerate(races):
        runners = race["runners"][:N]
        odds = [x["odds"] for x in runners]
        p = market.devig_power(odds)
        n = len(runners)
        logp[r, :n] = np.log(np.clip(p, 1e-9, None))
        for i, x in enumerate(runners):
            f = x.get("features") or {}
            raw[r, i] = [np.nan if f.get(k) is None else f[k] for k in names]
        for i, pos in enumerate(race["finish"][:N]):
            ok[r, i] = pos is not None
        fin = [i for i in race["order"] if i < N][:STAGES]
        order[r, :len(fin)] = fin
    if stats is None:
        flat = raw.reshape(-1, Fn)[ok.reshape(-1)] if Fn else np.zeros((0, 0))
        mean = np.nanmean(flat, axis=0) if Fn else np.zeros(0)
        std = np.nanstd(flat, axis=0) if Fn else np.zeros(0)
        mean = np.where(np.isfinite(mean), mean, 0.0)
        std = np.where(np.isfinite(std) & (std > 0), std, 1.0)
        stats = {"mean": mean.tolist(), "std": std.tolist()}
    mean, std = np.asarray(stats["mean"]), np.asarray(stats["std"])
    if Fn:
        X = (raw - mean) / std
        X[~np.isfinite(X)] = 0.0
    # per race: its own race-type / field-size discounts when tagged (calibrate.fit_segment_discounts)
    lam = np.array([positions.stage_discounts(STAGES, race.get("discounts") or discounts) for race in races])
    lam = lam.reshape(R, STAGES)
    return {"logp": logp, "X": X, "ok": ok, "order": order, "lam": lam, "stats": stats}


def _loss_grad(theta, A, l2=L2):
    a, beta = theta[0], theta[1:]
    logp, X, ok, order, lam = A["logp"], A["X"], A["ok"], A["order"], A["lam"]
    R, N = logp.shape
    u = a * logp + (X @ beta if len(beta) else 0.0)
    feats = np.concatenate([logp[:, :, None], X], axis=2)        # (R,N,1+F)
    left = ok.copy()
    rows = np.arange(R)
    ll = 0.0
    grad = np.zeros_like(theta)
    count = 0
    for s in range(STAGES):
        pick = order[:, s]
        live = (pick >= 0) & (left.sum(1) >= 2)
        if not live.any():
            break
        ls = lam[:, s]
        z = np.where(left, ls[:, None] * u, -np.inf)
        zmax = z.max(1, keepdims=True)
        e = np.exp(z - zmax)
        P = e / e.sum(1, keepdims=True)
        lse = (zmax[:, 0] + np.log(e.sum(1)))
        idx = np.where(live, pick, 0)
        ll += (ls * u[rows, idx] - lse)[live].sum()
        chosen = feats[rows, idx]                                 # (R,1+F)
        expected = np.einsum("rn,rnf->rf", P, feats)
        grad += (ls[:, None] * (chosen - expected))[live].sum(0)
        count += live.sum()
        left[rows[live], pick[live]] = False
    loss = -ll / max(1, count) + l2 * float(beta @ beta)
    g = -grad / max(1, count)
    g[1:] += 2 * l2 * beta
    return loss, g


def fit(races: list[dict], names: Sequence[str], discounts, l2: float = L2) -> dict:
    A = _arrays(races, names, discounts)
    theta0 = np.zeros(1 + len(names))
    theta0[0] = 1.0
    res = minimize(_loss_grad, theta0, args=(A, l2), jac=True, method="L-BFGS-B")
    base, _ = _loss_grad(theta0, A, 0.0)
    return {"kind": "exploded", "fitted": True, "features": ["log_market_p", *names],
            "weights": [round(float(w), 6) for w in res.x], "stats": A["stats"],
            "n_races": len(races), "train_loss": round(float(res.fun), 6), "market_loss": round(float(base), 6)}


def loss(races: list[dict], blend: Optional[dict], discounts) -> float:
    """Average per-stage negative log likelihood of the first six finishers (lower is better)."""
    names = blend["features"][1:] if blend else []
    A = _arrays(races, names, discounts, blend["stats"] if blend else None)
    theta = np.asarray(blend["weights"], float) if blend else np.array([1.0])
    return float(_loss_grad(theta, A, 0.0)[0])


def select(train: list[dict], valid: list[dict], discounts, groups: Optional[dict] = None, log=print) -> dict:
    """Forward selection of feature groups on held-back races."""
    groups = groups or F.GROUPS
    chosen: list[str] = []
    best = loss(valid, fit(train, [], discounts), discounts)
    log(f"  market only                  validation loss {best:.5f}")
    report = {"market_only": best}
    for g, cols in groups.items():
        trial = fit(train, chosen + cols, discounts)
        v = loss(valid, trial, discounts)
        keep = v < best - MIN_GAIN
        log(f"  + {g:<26} validation loss {v:.5f}  {'kept' if keep else 'dropped'}")
        report[g] = {"loss": v, "kept": keep}
        if keep:
            chosen, best = chosen + cols, v
    return {"features": chosen, "validation_loss": best, "steps": report}


def apply(p_win, runners: Sequence[dict], blend: Optional[dict]) -> np.ndarray:
    """Market probabilities -> learned win probabilities (unchanged without a fitted model)."""
    p = np.asarray(p_win, float)
    if not blend or not blend.get("fitted") or blend.get("kind") != "exploded":
        return p
    names = blend["features"][1:]
    w = np.asarray(blend["weights"], float)
    mean, std = np.asarray(blend["stats"]["mean"]), np.asarray(blend["stats"]["std"])
    u = w[0] * np.log(np.clip(p, 1e-9, None))
    if names:
        raw = np.array([[np.nan if (r.get("features") or {}).get(k) is None else r["features"][k] for k in names]
                        for r in runners], float)
        Z = (raw - mean) / std
        Z[~np.isfinite(Z)] = 0.0
        u = u + Z @ w[1:]
    e = np.exp(u - u.max())
    return e / e.sum()


def tag_segments(races: list[dict], segments: Optional[dict]) -> None:
    """Give each dataset race its race-type / field-size discounts (or clear them with None)."""
    from racing.calibrate import segment

    for race in races:
        d = (segments or {}).get(segment(race.get("race_type"), len(race["runners"])))
        if d:
            race["discounts"] = d
        else:
            race.pop("discounts", None)


def importance(blend: dict) -> list:
    """Features by the size of their weight (per standard deviation), largest first."""
    return sorted(zip(blend["features"][1:], blend["weights"][1:]), key=lambda x: -abs(x[1]))
