#!/usr/bin/env python3
"""
How good is the 2-up % at predicting 2-ups, and does backing with a 2UP early
payout (no lay) make money?

A 2UP back pays as a winner if the team wins OR goes 2 goals up at any point.
Point-in-time: the FTA model (same inputs and recency as the live model) is fitted
on everything before the last 2 seasons and scored on those seasons.

  1. Accuracy of the 2-up %: predicted vs actual by band, ranking (AUC) vs the
     market's win chance as a predictor of 2-ups
  2. Back every side with 2UP at the market average price: return overall and by
     2-up % band, FTA% band and odds band, next to the same bets WITHOUT 2UP

Prices are the market average before kick-off (match_odds). Bookmakers that offer
2UP are often a little below the best price, so treat small edges with care.

    venv/bin/python -u scripts/two_up_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import fta_path_model as fm  # noqa: E402

STAKE = 10.0


def sides(test_years=2):
    """[{p_up2, fta, odds, won, up2, paid}] for test-window sides with odds."""
    matches = fm.load_matches()
    rows, _, _ = fm.replay(matches)
    bundle = fm.load_bundle() or {}
    feats = bundle.get("features") or fm.BASE_FEATURES
    half_life = bundle.get("recency_half_life_days")
    if not rows:
        return []
    last = max(r["day"] for r in rows)
    split = last - 365 * test_years
    train = [r for r in rows if r["day"] < split]
    ma, mb, _, _ = fm._fit_pair(train, feats, half_life)
    out = []
    for i, m in enumerate(matches):
        if m["day"] < split or not m.get("odds") or not all(m["odds"]):
            continue
        for side, odds, won in ((1, m["odds"][0], m["fh"] > m["fa"]), (2, m["odds"][2], m["fa"] > m["fh"])):
            r = rows[2 * i + side - 1]
            X = np.array([[r[f] for f in feats]], dtype=float)
            if not np.all(np.isfinite(X)):
                X = np.nan_to_num(X)
            p_up2 = float(fm._predict_stage(ma, None, X)[0])
            p_fail = float(fm._predict_stage(mb, None, X)[0])
            out.append({"p_up2": p_up2, "fta": p_up2 * p_fail, "odds": float(odds), "won": int(won),
                        "up2": r["up2"], "paid": int(won or r["up2"]), "mkt_win": r.get("mkt_win")})
    return out


def _auc(s, y):
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y, s))
    except ValueError:
        return float("nan")


def _roi(sel, key):
    if not sel:
        return None
    profit = sum(STAKE * (s["odds"] - 1) if s[key] else -STAKE for s in sel)
    return profit, profit / (STAKE * len(sel))


def report(ss):
    if not ss:
        print("No test sides with odds.")
        return
    y = [s["up2"] for s in ss]
    print(f"2-up test: {len(ss)} team-sides in the last 2 seasons with odds")
    print(f"  Went 2 up: actual {100 * np.mean(y):.1f}%   predicted {100 * np.mean([s['p_up2'] for s in ss]):.1f}%")
    mk = [(s["mkt_win"], s["up2"]) for s in ss if s["mkt_win"] == s["mkt_win"] and s["mkt_win"] is not None]
    print(f"  Ranking 2-ups (AUC, 0.5 = chance): 2-up % {_auc([s['p_up2'] for s in ss], y):.3f}   "
          f"market win chance {_auc([a for a, _ in mk], [b for _, b in mk]):.3f}")
    print("  2-up % band | sides | predicted | actual 2-up | 2UP paid | ROI with 2UP | ROI without")
    for lo, hi in ((0, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 101)):
        sel = [s for s in ss if lo <= 100 * s["p_up2"] < hi]
        if not sel:
            continue
        r2, r0 = _roi(sel, "paid"), _roi(sel, "won")
        print(f"  {lo:>2}-{hi if hi < 101 else 100:<3}%     | {len(sel):>5} | {100 * np.mean([s['p_up2'] for s in sel]):8.1f}% | "
              f"{100 * np.mean([s['up2'] for s in sel]):10.1f}% | {100 * np.mean([s['paid'] for s in sel]):7.1f}% | "
              f"{100 * r2[1]:+11.1f}% | {100 * r0[1]:+10.1f}%")

    def table(title, key, bands, fmt):
        print(f"  {title:<12}| sides | 2UP paid | avg odds | profit with 2UP (ROI)  | ROI without")
        for lo, hi in bands:
            sel = [s for s in ss if lo <= key(s) < hi]
            if not sel:
                continue
            r2, r0 = _roi(sel, "paid"), _roi(sel, "won")
            print(f"  {fmt(lo, hi):<12}| {len(sel):>5} | {100 * np.mean([s['paid'] for s in sel]):7.1f}% | "
                  f"{np.mean([s['odds'] for s in sel]):8.2f} | £{r2[0]:>8.0f} ({100 * r2[1]:+5.1f}%) | {100 * r0[1]:+10.1f}%")

    table("FTA% band", lambda s: 100 * s["fta"], ((0, 1), (1, 1.8), (1.8, 2.5), (2.5, 3), (3, 4), (4, 100)),
          lambda lo, hi: f"{lo:g}-{hi:g}%" if hi < 100 else f"{lo:g}%+")
    table("Odds band", lambda s: s["odds"], ((1, 1.5), (1.5, 2), (2, 2.5), (2.5, 3.5), (3.5, 5), (5, 1000)),
          lambda lo, hi: f"{lo:g}-{hi:g}" if hi < 1000 else f"{lo:g}+")
    all2, all0 = _roi(ss, "paid"), _roi(ss, "won")
    print(f"  Every side: with 2UP {100 * all2[1]:+.1f}%   without {100 * all0[1]:+.1f}%  "
          f"(the gap is what the 2UP payout is worth at average prices)")
    print("  A real edge = a band clearly above 0% with 2UP over a few hundred bets. Average prices include the")
    print("  bookmaker margin; your 2UP bookmaker's price may be a little better or worse.")


def main():
    report(sides())


if __name__ == "__main__":
    main()
