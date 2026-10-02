"""
Non-finishers: in jumps races a share of runners fall, unseat or are pulled up,
and a non-finisher is never placed. That matters more for 4th-6th than for 3rd.

Rates depend on race type and price (outsiders fail to finish more often).
Defaults below are rough priors; fit_rates() replaces them from results.
"""

from __future__ import annotations

from typing import Optional, Sequence

BANDS = (5.0, 10.0, 20.0, 50.0)     # decimal-odds upper edges; last band is 50+
DEFAULT_RATES = {
    "flat": [0.002, 0.002, 0.003, 0.004, 0.006],
    "hurdle": [0.02, 0.03, 0.05, 0.08, 0.12],
    "chase": [0.05, 0.07, 0.10, 0.14, 0.20],
}
MIN_RUNNERS_PER_CELL = 300


def race_type(*labels) -> str:
    text = " ".join(str(x or "") for x in labels).lower()
    if "chase" in text:
        return "chase"
    if "hurdle" in text:
        return "hurdle"
    return "flat"   # flat and NH flat (bumpers): non-finishers are rare


def band(odds: float) -> int:
    for i, edge in enumerate(BANDS):
        if odds < edge:
            return i
    return len(BANDS)


def rates_for(odds: Sequence[float], rtype: str, table: Optional[dict] = None) -> list:
    t = (table or DEFAULT_RATES).get(rtype) or DEFAULT_RATES.get(rtype) or DEFAULT_RATES["flat"]
    return [float(t[band(o)]) for o in odds]


def fit_rates(races: list[dict]) -> dict:
    """races: datasets.load_races output. Cells with too few runners keep the default."""
    counts = {k: [[0, 0] for _ in range(len(BANDS) + 1)] for k in DEFAULT_RATES}
    for r in races:
        cells = counts[r.get("race_type") or "flat"]
        for runner, pos in zip(r["runners"], r["finish"]):
            c = cells[band(runner["odds"])]
            c[0] += 1
            c[1] += pos is None
    table = {}
    for k, cells in counts.items():
        table[k] = [round(dnf / n, 4) if n >= MIN_RUNNERS_PER_CELL else DEFAULT_RATES[k][i]
                    for i, (n, dnf) in enumerate(cells)]
    table["runners"] = {k: sum(c[0] for c in cells) for k, cells in counts.items()}
    return table
