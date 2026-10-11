#!/usr/bin/env python3
"""
Lay-the-draw market test for Goal Likelihood (models/goal_likelihood.py).

Uses past games with stored 1X2 odds (match_odds: football-data market average
before kick-off). Everything is point-in-time: the model only knows games before
each match, and its calibration is fitted on seasons before the test window.

Lay price = the market's fair draw price (bookmaker margin removed) + 1.5%, roughly
where the Betfair lay sits. Commission on net winnings (default 2%).

Two ways of playing it, £10 lay stake each game:
  hold    lay before kick-off, keep it to full time (win unless it's a draw)
  trade   lay before kick-off; straight after the first goal back the draw to
          lock in the same result either way; still 0-0 at --exit minutes: trade
          out at 0-0 for a loss. In-play draw prices are SIMULATED (Poisson from
          the market's pre-match goal expectation, minus a 2% spread), not real
          Betfair prices, so treat the trade numbers as rough.

    venv/bin/python -u scripts/lay_draw_test.py
    venv/bin/python -u scripts/lay_draw_test.py --commission 5 --exit 70
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import goal_likelihood as gl  # noqa: E402

STAKE = 10.0
LAY_MARKUP = 1.015
INPLAY_SPREAD = 0.98


def _pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def draw_prob(lam_h, lam_a, lead=0):
    """P(final draw) when the home side leads by `lead` and lam_* goals remain."""
    tot = 0.0
    for j in range(12):
        i = j - lead
        if i >= 0:
            tot += _pois(lam_h, i) * _pois(lam_a, j)
    return tot


def market_fair(odds):
    """1X2 average odds -> fair (margin removed) probabilities."""
    h, d, a = (1 / float(o) for o in odds)
    s = h + d + a
    return h / s, d / s, a / s


_GRID = None


def _grid():
    """(lam_h, lam_a, P(draw), P(home win)) over a grid of goal expectations, built once."""
    global _GRID
    if _GRID is None:
        rows = []
        k = np.arange(12)
        fact = np.array([math.factorial(int(i)) for i in k], float)
        for th in np.arange(1.0, 4.6, 0.05):
            for sh in np.arange(0.2, 0.81, 0.01):
                lh, la = th * sh, th * (1 - sh)
                ph = np.exp(-lh) * lh ** k / fact
                pa = np.exp(-la) * la ** k / fact
                joint = np.outer(ph, pa)
                rows.append((lh, la, float(np.trace(joint)), float(np.tril(joint, -1).sum())))
        _GRID = np.array(rows)
    return _GRID


def market_lambdas(p_h, p_d, p_a):
    """Goal expectations whose Poisson matches the market's home / draw / away."""
    g = _grid()
    i = int(np.argmin((g[:, 2] - p_d) ** 2 + (g[:, 3] - p_h) ** 2))
    return float(g[i, 0]), float(g[i, 1])


def _net(x, commission):
    return x * (1 - commission) if x > 0 else x


def hold_pl(lay, is_draw, commission):
    return -STAKE * (lay - 1) if is_draw else _net(STAKE, commission)


def trade_pl(lay, lam, goals, final_draw, exit_minute, commission):
    """Lay STAKE at `lay`, then green up after the first goal (or at exit_minute at 0-0)."""
    first = goals[0] if goals else None
    if first is not None and (first[0] or 0) <= exit_minute:
        t, lead = first[0] or 0, (1 if first[1] == 1 else -1)
    else:   # still 0-0 at the exit minute
        t, lead = exit_minute, 0
    r = max(0.0, (90 - t) / 90)
    p = draw_prob(lam[0] * r, lam[1] * r, lead)
    back = max(1.01, (1 / max(p, 1e-6)) * INPLAY_SPREAD)
    green = STAKE - STAKE * lay / back        # same on both outcomes after backing STAKE*lay/back
    return _net(green, commission)


def run(matches, commission=0.02, exit_minute=70, test_years=2):
    st, rows = gl.walk(matches)
    rows = gl._usable(rows)
    if not rows:
        return None
    split = rows[-1][0]["day"] - 365 * test_years
    train = [r for r in rows if r[0]["day"] < split]
    test = [r for r in rows if r[0]["day"] >= split and r[0].get("odds") and all(r[0]["odds"])
            and r[0].get("goals") is not None]
    cal = gl.fit_calibration(train)
    # model draw chance, calibrated on training seasons
    tr = [(draw_prob(r[1]["xg_home"], r[1]["xg_away"]), int(r[0]["fh"] == r[0]["fa"])) for r in train]
    draw_cal = gl.fit_platt(*zip(*tr)) if len(tr) >= 500 else None

    games = []
    for m, pred, out in test:
        try:
            ph, pd_, pa = market_fair(m["odds"])
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        lay = (1 / pd_) * LAY_MARKUP
        lam = market_lambdas(ph, pd_, pa)
        p = gl.calibrated(pred["raw"], cal)
        model_d = gl.apply_platt(draw_prob(pred["xg_home"], pred["xg_away"]), draw_cal)
        is_draw = m["fh"] == m["fa"]
        games.append({
            "score": gl.goal_score(p), "model_d": model_d, "market_d": pd_, "lay": lay, "draw": int(is_draw),
            "hold": hold_pl(lay, is_draw, commission),
            "trade": trade_pl(lay, lam, m["goals"], is_draw, exit_minute, commission),
        })
    return games


def summarise(games):
    n = len(games)
    if not n:
        return None
    liab = sum(STAKE * (g["lay"] - 1) for g in games)
    return {"n": n, "draws": sum(g["draw"] for g in games) / n,
            "avg_lay": sum(g["lay"] for g in games) / n,
            "hold": sum(g["hold"] for g in games), "trade": sum(g["trade"] for g in games),
            "hold_roi": sum(g["hold"] for g in games) / liab, "trade_roi": sum(g["trade"] for g in games) / liab}


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def report(games, commission, exit_minute):
    if not games:
        print("No test games with odds and goal timelines.")
        return
    y = [g["draw"] for g in games]
    print(f"Lay-the-draw test: {len(games)} games in the last 2 seasons with odds "
          f"(£{STAKE:.0f} lay each, {100 * commission:.0f}% commission, trade-out exit {exit_minute}')")
    print(f"  Draw chance accuracy (log loss, lower = better): model {_ll([g['model_d'] for g in games], y):.4f}"
          f"  market {_ll([g['market_d'] for g in games], y):.4f}  "
          f"actual draws {100 * np.mean(y):.1f}%")
    q = np.quantile([g["score"] for g in games], 0.8)
    filters = [
        ("All games", lambda g: True),
        ("Top 20% goal score", lambda g: g["score"] >= q),
        ("Model draw 2pp+ below market", lambda g: g["model_d"] <= g["market_d"] - 0.02),
        ("Model draw 4pp+ below market", lambda g: g["model_d"] <= g["market_d"] - 0.04),
        ("Draw lay 3.0-4.0", lambda g: 3.0 <= g["lay"] <= 4.0),
        ("Draw lay 3.0-4.0 + top 20% score", lambda g: 3.0 <= g["lay"] <= 4.0 and g["score"] >= q),
        ("Top 20% score + model 2pp below", lambda g: g["score"] >= q and g["model_d"] <= g["market_d"] - 0.02),
    ]
    print("  filter                          |    n | draws | avg lay | hold P/L (ROI)    | trade P/L (ROI)")
    for name, f in filters:
        s = summarise([g for g in games if f(g)])
        if not s:
            continue
        print(f"  {name:<31} | {s['n']:>4} | {100 * s['draws']:4.1f}% | {s['avg_lay']:7.2f} | "
              f"£{s['hold']:>8.0f} ({100 * s['hold_roi']:+5.1f}%) | £{s['trade']:>8.0f} ({100 * s['trade_roi']:+5.1f}%)")
    print("  ROI is on liability. Hold uses real results; trade uses simulated in-play prices.")
    print("  Past results only - small edges this size are easily noise or wiped out by worse prices.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commission", type=float, default=2.0, help="exchange commission %%")
    ap.add_argument("--exit", type=int, default=70, help="0-0 at this minute: trade out for a loss")
    args = ap.parse_args()
    from models.fta_path_model import load_matches

    games = run(load_matches(), args.commission / 100, args.exit)
    report(games, args.commission / 100, args.exit)


if __name__ == "__main__":
    main()
