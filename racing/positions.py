"""
Position distribution engine: win probabilities -> P(finish k-th) for every runner.

Model: discounted Plackett-Luce (Harville with Benter / Lo-Bacon-Shone
discounts). Positions are filled one at a time; at stage s the next finisher
is drawn from the runners still left with weight p_i ** lambda_s.
lambda_1 = 1 is plain Harville. lambda_s < 1 flattens the later stages,
which matches results far better: a big favourite that doesn't win is less
dominant for 2nd..6th than Harville assumes, and outsiders fill the minor
places more often.

Benter (1994) reported about 0.81 for 2nd and 0.65 for 3rd. 4th onwards has
no published consensus, so the defaults below continue the decay gently and
should be replaced by fitted values (racing/calibrate.py) once results are
loaded.

Sampling uses the Gumbel-max trick: argmax(lambda_s * log p_i + G_i) over the
runners left is an exact draw from p ** lambda_s renormalised. Simulations run
in batches so the spread between batches measures simulation noise.
"""

from __future__ import annotations

from itertools import permutations
from typing import Optional, Sequence

import numpy as np

DEFAULT_DISCOUNTS = (1.0, 0.81, 0.65, 0.58, 0.53, 0.50)
N_SIMS = 10_000


def stage_discounts(n: int, discounts: Optional[Sequence[float]] = None) -> np.ndarray:
    d = list(discounts or DEFAULT_DISCOUNTS)
    if not d:
        d = [1.0]
    return np.array([d[min(s, len(d) - 1)] for s in range(n)], dtype=float)


def simulate_orders(p_win: Sequence[float], n_sims: int = N_SIMS,
                    discounts: Optional[Sequence[float]] = None,
                    seed: Optional[int] = 7, depth: Optional[int] = None) -> np.ndarray:
    """(n_sims, depth) array of runner indices in finishing order."""
    p = np.clip(np.asarray(p_win, dtype=float), 1e-9, None)
    n = len(p)
    depth = n if depth is None else min(depth, n)
    lam = stage_discounts(n, discounts)
    logp = np.log(p)
    rng = np.random.default_rng(seed)
    taken = np.zeros((n_sims, n), dtype=bool)
    orders = np.empty((n_sims, depth), dtype=np.int16)
    rows = np.arange(n_sims)
    for s in range(depth):
        g = rng.gumbel(size=(n_sims, n))
        score = lam[s] * logp + g
        score[taken] = -np.inf
        pick = score.argmax(axis=1)
        orders[:, s] = pick
        taken[rows, pick] = True
    return orders


def position_matrix(orders: np.ndarray, n: int) -> np.ndarray:
    """orders (sims, depth) -> P[i, k] = share of sims runner i finished k-th."""
    sims, depth = orders.shape
    P = np.zeros((n, depth))
    for k in range(depth):
        P[:, k] = np.bincount(orders[:, k], minlength=n) / sims
    return P


def simulate(p_win: Sequence[float], n_sims: int = N_SIMS,
             discounts: Optional[Sequence[float]] = None,
             seed: Optional[int] = 7, depth: Optional[int] = None,
             batches: int = 10) -> dict:
    """
    Returns
      P        (n, depth) position probabilities
      top      (n, depth) cumulative P(finish in top k), column k-1 = top k
      top_se   (n, depth) Monte Carlo standard error of `top` (from batch spread)
      n_sims
    """
    n = len(p_win)
    orders = simulate_orders(p_win, n_sims, discounts, seed, depth)
    d = orders.shape[1]
    P = position_matrix(orders, n)
    top = np.cumsum(P, axis=1)
    batches = max(2, min(batches, n_sims // 100 or 2))
    tops = np.stack([
        np.cumsum(position_matrix(chunk, n), axis=1)
        for chunk in np.array_split(orders, batches)
    ])
    top_se = tops.std(axis=0, ddof=1) / np.sqrt(batches)
    return {"P": P, "top": top, "top_se": top_se, "n_sims": n_sims, "depth": d}


def exact_positions(p_win: Sequence[float], discounts: Optional[Sequence[float]] = None) -> np.ndarray:
    """Exact discounted-Harville position matrix by enumeration (small fields only; tests)."""
    p = np.asarray(p_win, dtype=float)
    n = len(p)
    if n > 8:
        raise ValueError("exact_positions is for fields of 8 or fewer")
    lam = stage_discounts(n, discounts)
    P = np.zeros((n, n))
    for order in permutations(range(n)):
        prob = 1.0
        left = list(range(n))
        for s, i in enumerate(order):
            w = p[left] ** lam[s]
            prob *= (p[i] ** lam[s]) / w.sum()
            left.remove(i)
        for s, i in enumerate(order):
            P[i, s] += prob
    return P
