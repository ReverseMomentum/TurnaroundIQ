"""
Robust Kelly staking.

Kelly maximises long-run log growth when the probabilities are right. They are
estimates, so staking uses the lower edge of the uncertainty band (p - z * se)
instead of the point estimate: an uncertain edge gets a smaller stake, and an
edge that does not survive the band gets none. The result is then scaled by
the chosen fraction (quarter / half / full Kelly).

Two bets are covered:
  place only  binary, closed form
  each-way    three outcomes (won, placed only, unplaced), solved numerically
"""

from __future__ import annotations

import math

from scipy.optimize import minimize_scalar

FRACTIONS = {"quarter": 0.25, "half": 0.5, "full": 1.0}
MAX_STAKE_PCT = 0.05  # never suggest more than 5% of bankroll on one runner
# Longer prices carry more model error (and a wrong price inflates the edge most there),
# so the cap shrinks with the odds: 5% up to 8/1, then 0.45 / decimal odds
# (about 2.5% at 17/1, 1.7% at 25/1, 1.3% at 33/1).
LONGSHOT_CAP_NUMERATOR = 0.45


def stake_cap(win_odds: float) -> float:
    return min(MAX_STAKE_PCT, LONGSHOT_CAP_NUMERATOR / max(float(win_odds), 1.01))


def kelly_binary(p: float, odds: float) -> float:
    b = odds - 1.0
    if b <= 0 or p <= 0:
        return 0.0
    return max(0.0, (p * b - (1 - p)) / b)


def kelly_each_way(p_win: float, p_place: float, win_odds: float, place_odds: float) -> float:
    """Share of bankroll for the whole each-way stake (half on each part)."""
    p_win = min(max(p_win, 0.0), 1.0)
    p_place = min(max(p_place, p_win), 1.0)
    a = 0.5 * (win_odds - 1.0) + 0.5 * (place_odds - 1.0)   # won
    b = 0.5 * (place_odds - 1.0) - 0.5                         # placed, not won
    ev = p_win * a + (p_place - p_win) * b - (1 - p_place)
    if ev <= 0:
        return 0.0

    def neg_growth(f):
        g = (1 - p_place) * math.log(1 - f) + p_win * math.log(1 + f * a)
        if p_place > p_win:
            g += (p_place - p_win) * math.log(max(1e-12, 1 + f * b))
        return -g

    hi = 0.999 if b >= 0 else min(0.999, 0.999 / -b)
    res = minimize_scalar(neg_growth, bounds=(0.0, hi), method="bounded")
    return max(0.0, float(res.x))


def robust_stakes(p_win: float, p_place: float, se_win: float, se_place: float,
                  win_odds: float, place_odds: float, z: float = 1.0) -> dict:
    """Kelly shares (of bankroll) on the lower edge of the band, for each fraction."""
    pw = max(0.0, p_win - z * se_win)
    pp = max(pw, p_place - z * se_place)
    full_place = kelly_binary(pp, place_odds)
    full_ew = kelly_each_way(pw, pp, win_odds, place_odds)
    cap = stake_cap(win_odds)
    out = {}
    for name, frac in FRACTIONS.items():
        out[name] = {
            "place_only_pct": round(100 * min(cap, frac * full_place), 2),
            "each_way_pct": round(100 * min(cap, frac * full_ew), 2),
        }
    return out
