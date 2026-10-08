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


# A back/lay gap wider than this means the market has not formed: early in the day
# Betfair often shows a stray back offer against no real lay (e.g. 5.1 / 600), and
# the midpoint of that is meaningless.
MAX_SPREAD = 0.25
FORMED_SHARE = 0.8   # a race's market counts as formed when this share of runners are


def formed(back: Optional[float], lay: Optional[float]) -> bool:
    return bool(back and lay and back > 1 and lay >= back and lay / back - 1 <= MAX_SPREAD)


def exchange_price_prob(back: Optional[float], lay: Optional[float]) -> Optional[float]:
    """Midpoint when the market is formed; the back price alone when it is not (the lay side is
    an empty book, so it says nothing)."""
    if formed(back, lay):
        return exchange_mid(back, lay)
    return implied(back)


def best_price(book_odds: dict) -> Optional[float]:
    vals = [float(v) for v in (book_odds or {}).values() if implied(v)]
    return max(vals) if vals else None


def _formed_share(ex: Sequence[Optional[float]], is_formed: Sequence[bool]) -> float:
    """Share of the field's win chance sitting on runners with a formed Betfair market."""
    w = [float(x or 0.0) for x in ex]
    total = sum(w)
    if total <= 0:
        return sum(is_formed) / max(1, len(is_formed))
    return sum(x for x, f in zip(w, is_formed) if f) / total


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
    ex = [exchange_price_prob((r.get("exchange") or {}).get("back"), (r.get("exchange") or {}).get("lay"))
          for r in runners]
    is_formed = [formed((r.get("exchange") or {}).get("back"), (r.get("exchange") or {}).get("lay")) for r in runners]
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
        "formed": is_formed,
        # weighted by chance: a few unformed 100/1 shots shouldn't mark a whole race as thin
        "formed_share": _formed_share(ex, is_formed),
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


# ---- estimated bookmaker prices (no bookmaker feed) --------------------------
# Betfair has no each-way bets and its prices carry no bookmaker margin, so an
# exchange price overstates what a bookmaker will offer. Without a bookmaker
# price, the engine prices offers at an estimate: the exchange's fair chances
# inflated to a typical bookmaker book (more on outsiders: the favourite-longshot
# bias bookmakers price in), then rounded DOWN to a standard UK price.

UK_PRICES = sorted({1 + a / b for a, b in (
    (1, 5), (2, 9), (1, 4), (2, 7), (3, 10), (1, 3), (4, 11), (2, 5), (4, 9), (1, 2), (8, 15), (4, 7), (8, 13),
    (4, 6), (8, 11), (4, 5), (5, 6), (10, 11), (1, 1), (11, 10), (6, 5), (5, 4), (11, 8), (6, 4), (13, 8), (7, 4),
    (15, 8), (2, 1), (9, 4), (5, 2), (11, 4), (3, 1), (10, 3), (7, 2), (4, 1), (9, 2), (5, 1), (11, 2), (6, 1),
    (13, 2), (7, 1), (15, 2), (8, 1), (17, 2), (9, 1), (10, 1), (11, 1), (12, 1), (14, 1), (16, 1), (18, 1), (20, 1),
    (22, 1), (25, 1), (28, 1), (33, 1), (40, 1), (50, 1), (66, 1), (80, 1), (100, 1))})


def uk_price_at_most(d: float) -> Optional[float]:
    """Largest standard UK price (decimal) not above d."""
    below = [x for x in UK_PRICES if x <= d + 1e-9]
    return below[-1] if below else None


def uk_price_nearest(d: float) -> float:
    """Nearest standard UK price (by ratio): the estimate's margin is already taken off, so
    rounding down too would cut outsiders twice (19.9 -> 15.0 instead of 21.0)."""
    return min(UK_PRICES, key=lambda x: abs(np.log(x) - np.log(max(d, 1.01))))


def typical_overround(n: int, table: Optional[dict] = None) -> float:
    """Typical bookmaker book for an n-runner race: fitted from SP (calibration) if given, else ~1 + 1.8% a runner."""
    if table:
        keys = sorted(int(k) for k in table)
        k = min(keys, key=lambda x: abs(x - n))
        return float(table[str(k)] if str(k) in table else table[k])
    return min(1.45, max(1.08, 1.0 + 0.018 * n))


def book_from_fair(p_fair: Sequence[float], overround: float) -> np.ndarray:
    """Fair chances -> bookmaker chances q = p^k with sum(q) = overround (k < 1 inflates outsiders more)."""
    p = np.clip(np.asarray(p_fair, float), 1e-6, 1.0)
    if overround <= 1.0 or len(p) < 2:
        return p
    lo, hi = 0.2, 1.0
    for _ in range(80):
        k = 0.5 * (lo + hi)
        if np.power(p, k).sum() > overround:
            lo = k
        else:
            hi = k
    return np.power(p, 0.5 * (lo + hi))


def early_book_from_fair(p_fair: Sequence[float], overround: float) -> np.ndarray:
    """Early-price book: half SP-style longshot squeeze (power), half an even cut. SP squeezes
    outsiders hard (~30% off a 25/1 shot); early extra-place prices are flatter (~20-25%)."""
    p = np.clip(np.asarray(p_fair, float), 1e-6, 1.0)
    return 0.5 * book_from_fair(p, overround) + 0.5 * p * max(1.0, overround)


def best_price_overround(n: int) -> float:
    """Book of the BEST price across the firms offering the extra place (the price a bettor
    shopping around takes): close to the exchange, ~100% + 0.6% a runner, not a single firm's SP book."""
    return min(1.15, max(1.03, 1.0 + 0.006 * n))


def estimated_book_odds(p_fair: Sequence[float], table: Optional[dict] = None) -> list:
    """Estimated best bookmaker price per runner. `table` (fitted single-firm SP books) is kept
    for reference but not used: the bettor takes the best price, not a typical firm's."""
    p = np.clip(np.asarray(p_fair, float), 1e-6, 1.0)
    q = early_book_from_fair(p, best_price_overround(len(p)))
    # nearest UK price, but never at or above the fair price (that would be no margin at all)
    return [n if n < 1.0 / f else uk_price_at_most(1.0 / x)
            for n, x, f in ((uk_price_nearest(1.0 / x), x, f) for x, f in zip(q, p))]
