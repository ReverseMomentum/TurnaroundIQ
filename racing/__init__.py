"""
The Stables: horse racing extra-place value model.

Not a winner model. It estimates each runner's chance of finishing in every
position (P1..PN), then compares the chance of landing in a bookmaker's paid
places (including promotional extra places) with the price the bookmaker's
each-way terms imply.

Pipeline (see racing/engine.py):
  market.py      win prices -> fair win probabilities (overround removed)
  positions.py   discounted Plackett-Luce / Harville Monte Carlo -> P1..PN
  calibrate.py   fits the position discounts (and an optional form blend)
                 on past results; scores Brier / log loss / calibration
  extra_place.py each-way terms -> market place probability, edge, EV
  confidence.py  0-100 agreement / stability score
  kelly.py       robust fractional Kelly stake
  store.py       SQLite tables (rac_*), import and persistence
"""
