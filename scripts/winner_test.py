#!/usr/bin/env python3
"""
Does Goal Likelihood's expected goals pick winners better than the market?

Point-in-time, last 2 seasons with 1X2 odds (match_odds, market average). From
each game's expected goals (models/goal_likelihood.py) Poisson gives home / draw
/ away chances; the market's chances are the odds with the margin removed.

  1. Picking the winner: how often the model's most likely result happened vs
     the market favourite, and how often the higher-xG side won
  2. Accuracy: log loss of home/draw/away chances (lower = better), model vs market
  3. Value: back every result the model rates X% above the market, at the
     market average price (a real best price is a little higher)
  4. xG gap: when one side's expected goals are far higher, how often it won,
     and what the market already implied

    venv/bin/python -u scripts/winner_test.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from models import goal_likelihood as gl  # noqa: E402
import lay_draw_test as ldt  # noqa: E402

RESULTS = ("home", "draw", "away")


def one_x_two(lam_h, lam_a):
    k = np.arange(12)
    fact = np.array([math.factorial(int(i)) for i in k], float)
    ph = np.exp(-lam_h) * lam_h ** k / fact
    pa = np.exp(-lam_a) * lam_a ** k / fact
    j = np.outer(ph, pa)
    h, d = float(np.tril(j, -1).sum()), float(np.trace(j))
    s = h + d + float(np.triu(j, 1).sum())
    return h / s, d / s, 1 - (h + d) / s


def games(matches, test_years=2):
    _, rows = gl.walk(matches)
    rows = gl._usable(rows)
    if not rows:
        return []
    split = rows[-1][0]["day"] - 365 * test_years
    out = []
    for m, pred, _ in rows:
        if m["day"] < split or not m.get("odds") or not all(m["odds"]):
            continue
        try:
            mk = ldt.market_fair(m["odds"])
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        res = 0 if m["fh"] > m["fa"] else 1 if m["fh"] == m["fa"] else 2
        out.append({"model": one_x_two(pred["xg_home"], pred["xg_away"]), "market": mk,
                    "odds": tuple(float(o) for o in m["odds"]), "result": res,
                    "xg_gap": pred["xg_home"] - pred["xg_away"]})
    return out


def _ll(ps, ys):
    return float(-np.mean([math.log(max(p[y], 1e-9)) for p, y in zip(ps, ys)]))


def report(gs):
    n = len(gs)
    if not n:
        print("No test games with odds.")
        return
    ys = [g["result"] for g in gs]
    pick_model = np.mean([int(np.argmax(g["model"]) == g["result"]) for g in gs])
    pick_market = np.mean([int(np.argmax(g["market"]) == g["result"]) for g in gs])
    decisive = [g for g in gs if abs(g["xg_gap"]) > 1e-9]
    higher_xg_won = np.mean([int((g["xg_gap"] > 0 and g["result"] == 0) or (g["xg_gap"] < 0 and g["result"] == 2))
                             for g in decisive])
    print(f"Winner test: {n} games in the last 2 seasons with odds")
    print(f"  Most likely result happened: model {100 * pick_model:.1f}%   market favourite {100 * pick_market:.1f}%")
    print(f"  Higher expected goals side won: {100 * higher_xg_won:.1f}%")
    print(f"  Accuracy (log loss, lower = better): model {_ll([g['model'] for g in gs], ys):.4f}"
          f"   market {_ll([g['market'] for g in gs], ys):.4f}")

    print("  Value: back results the model rates above the market, £10 at the market average price")
    print("  model vs market  |  bets | won   | profit  | ROI")
    for edge in (0.0, 0.05, 0.10, 0.20):
        bets = [(g["odds"][i], int(g["result"] == i)) for g in gs for i in range(3)
                if g["model"][i] > g["market"][i] * (1 + edge)]
        if not bets:
            continue
        profit = sum(10 * (o - 1) if w else -10 for o, w in bets)
        print(f"  {'+' + str(int(edge * 100)) + '% or more':<16} | {len(bets):>5} | {100 * np.mean([w for _, w in bets]):4.1f}% "
              f"| £{profit:>6.0f} | {100 * profit / (10 * len(bets)):+5.1f}%")

    print("  xG gap (home minus away) | games | stronger side won | market implied | model implied")
    for lo, hi in ((0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 9)):
        sel = [g for g in gs if lo <= abs(g["xg_gap"]) < hi]
        if not sel:
            continue
        side = lambda g: 0 if g["xg_gap"] >= 0 else 2  # noqa: E731
        won = np.mean([int(g["result"] == side(g)) for g in sel])
        mk = np.mean([g["market"][side(g)] for g in sel])
        md = np.mean([g["model"][side(g)] for g in sel])
        label = f"{lo:g}-{hi:g}" if hi < 9 else f"{lo:g}+"
        print(f"  {label:<24} | {len(sel):>5} | {100 * won:16.1f}% | {100 * mk:13.1f}% | {100 * md:12.1f}%")
    print("  Stronger side winning often is expected; the question is whether it beats what the market implied.")


def main():
    from models.fta_path_model import load_matches

    report(games(load_matches()))


if __name__ == "__main__":
    main()
