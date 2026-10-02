"""
Confidence engine: a 0-100 score for how much the numbers agree and hold
steady. It is not a probability of winning the bet.

Components, each 0..1:
  model        plain Harville vs discounted Harville give similar place chances
  simulation   Monte Carlo noise is small next to the place probability
  market       exchange and bookmaker win prices agree on this runner
               (0.5 when only one market is available)
  calibration  position discounts were fitted on enough past races
               (0.3 while running on the published-prior defaults)
"""

from __future__ import annotations

import math
from typing import Optional

WEIGHTS = {"model": 0.30, "simulation": 0.15, "market": 0.30, "calibration": 0.25}
CALIBRATION_FULL_RACES = 1500


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def components(p_place: float, p_place_harville: float, se_sim: float,
               p_win_book: Optional[float], p_win_exchange: Optional[float],
               calibration_races: int) -> dict:
    p = max(p_place, 0.01)
    model = 1.0 - min(1.0, 2.0 * abs(p_place - p_place_harville) / p)
    simulation = 1.0 - min(1.0, 10.0 * se_sim / p)
    if p_win_book is not None and p_win_exchange is not None:
        pw = max(0.005, 0.5 * (p_win_book + p_win_exchange))
        market = 1.0 - min(1.0, 3.0 * abs(p_win_book - p_win_exchange) / pw)
    else:
        market = 0.5
    if calibration_races > 0:
        calibration = 0.3 + 0.7 * min(1.0, calibration_races / CALIBRATION_FULL_RACES)
    else:
        calibration = 0.3
    return {k: round(_clip01(v), 3) for k, v in
            {"model": model, "simulation": simulation, "market": market, "calibration": calibration}.items()}


def score(parts: dict) -> int:
    return int(round(100 * sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)))


def place_uncertainty(p_place: float, p_place_harville: float, se_sim: float,
                      calibration_races: int) -> float:
    """
    One standard error for the place probability: simulation noise plus model
    uncertainty, taken as the Harville-vs-discounted gap (full gap on prior
    discounts, half once they are fitted).
    """
    model_gap = abs(p_place - p_place_harville) * (0.5 if calibration_races > 0 else 1.0)
    return math.sqrt(se_sim ** 2 + model_gap ** 2)


def label(conf: int) -> str:
    if conf >= 70:
        return "Solid"
    if conf >= 50:
        return "Fair"
    return "Thin"


def grade(each_way_ev: float, robust_edge: float, conf: int, stake_pct: float,
          calibrated: bool) -> str:
    """
    A-D opportunity grade from the each-way EV (the bet actually placed).
    A/B also need the place edge to survive the uncertainty band and a
    non-zero robust Kelly stake. A needs discounts fitted on real results.
    """
    sound = robust_edge > 0 and stake_pct > 0
    if each_way_ev >= 0.10 and sound and conf >= 60 and calibrated:
        return "A"
    if each_way_ev >= 0.04 and sound and conf >= 45:
        return "B"
    if each_way_ev > 0:
        return "C"
    return "D"
