"""
Win prices -> fair win probabilities.

Bookmaker win books carry an overround, and most of it sits on the outsiders
(the favourite-longshot bias). The power method removes it by finding k with
sum(p_i ** k) == 1, which shrinks longshots more than favourites. The
multiplicative method (divide by the book total) is kept for comparison.

Exchange prices are close to fair already; the back/lay midpoint is used and
then normalised.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

import numpy as np


def implied(odds: Optional[float]) -> Optional[float]:
    """Decimal odds -> raw implied probability (None for missing / invalid odds)."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or o <= 1.0:
        return None
    return 1.0 / o


def overround(odds: Iterable[float]) -> float:
    """Book total of implied probabilities (1.0 = fair, 1.20 = 20% over)."""
    return float(sum(implied(o) or 0.0 for o in odds))


def devig_multiplicative(odds: Sequence[float]) -> np.ndarray:
    p = np.array([implied(o) or 0.0 for o in odds], dtype=float)
    s = p.sum()
    return p / s if s > 0 else p


def devig_power(odds: Sequence[float], tol: float = 1e-10) -> np.ndarray:
    """Power-method de-vig: p_i = q_i ** k with sum == 1 (bisection on k)."""
    q = np.array([implied(o) or 0.0 for o in odds], dtype=float)
    live = q > 0
    if not live.any():
        return q
    total = q[live].sum()
    if abs(total - 1.0) < tol:
        return q / total
    lo, hi = (1.0, 10.0) if total > 1.0 else (0.05, 1.0)
    for _ in range(200):
        k = 0.5 * (lo + hi)
        s = np.power(q[live], k).sum()
        if abs(s - 1.0) < tol:
            break
        # s falls as k rises (all q < 1)
        if s > 1.0:
            lo = k
        else:
            hi = k
    out = np.zeros_like(q)
    out[live] = np.power(q[live], k)
    return out / out.sum()


def exchange_mid(back: Optional[float], lay: Optional[float]) -> Optional[float]:
    """Midpoint of back and lay in probability space (more stable than in odds)."""
    pb, pl = implied(back), implied(lay)
    if pb and pl:
        return 0.5 * (pb + pl)
    return pb or pl


def best_price(book_odds: dict) -> Optional[float]:
    vals = [float(v) for v in (book_odds or {}).values() if implied(v)]
    return max(vals) if vals else None


def fair_win_probs(runners: Sequence[dict]) -> tuple[np.ndarray, str, dict]:
    """
    runners: dicts with any of
      win_odds (single bookmaker price), odds {bookmaker: price},
      exchange {back, lay, volume}
    Returns (probabilities, source, diagnostics).

    Exchange midpoints are used when every runner has one; otherwise the best
    bookmaker price per runner, power de-vigged. Both are reported so the
    confidence engine can measure how far the two markets agree.
    """
    n = len(runners)
    ex = [exchange_mid((r.get("exchange") or {}).get("back"), (r.get("exchange") or {}).get("lay")) for r in runners]
    book = [r.get("win_odds") or best_price(r.get("odds") or {}) for r in runners]

    p_book = None
    if all(implied(o) for o in book):
        p_book = devig_power(book)
    p_ex = None
    if all(ex):
        arr = np.array(ex, dtype=float)
        p_ex = arr / arr.sum()

    diag = {
        "book_overround": overround(book) if p_book is not None else None,
        "exchange_overround": float(sum(ex)) if p_ex is not None else None,
        "p_book": p_book,
        "p_exchange": p_ex,
    }
    if p_ex is not None:
        return p_ex, "exchange", diag
    if p_book is not None:
        return p_book, "bookmaker", diag
    # Partial prices: price what we can, spread the rest evenly over the unpriced.
    raw = np.array([(e or implied(b) or 0.0) for e, b in zip(ex, book)], dtype=float)
    missing = raw == 0
    if missing.all():
        return np.full(n, 1.0 / n), "uniform", diag
    known = raw[~missing].sum()
    fill = max(0.0, 1.0 - min(known, 0.98)) / max(1, missing.sum())
    raw[missing] = max(fill, 0.005)
    return raw / raw.sum(), "partial", diag
