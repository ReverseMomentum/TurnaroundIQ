#!/usr/bin/env python3
"""
Lay the draw, cash out after the first goal, with REAL Betfair prices
(logged each minute by collectors/betfair_inplay.py).

For each logged game:
  lay      the last draw lay price before kick-off
  goal     the first logged minute the score shows a goal; we back the draw at the
           NEXT logged snapshot (about a minute later: the price has settled and
           that's roughly when a person could act)
  0-0      still 0-0 at --exit minutes: back the draw then, for a loss
  hold     the same lay kept to full time, for comparison

"Drift vs expected": the draw back price after the first goal divided by what the
kick-off prices imply it should be (Poisson goals fitted to the kick-off home /
draw / away prices). Above 1.00 = the draw drifted MORE than the kick-off market
implied (good for this strategy, a sign of overreaction); below = less.

Prices come from the delayed Betfair key: snapshot times can lag the real market.

    venv/bin/python -u scripts/inplay_drift_report.py
    venv/bin/python -u scripts/inplay_drift_report.py --commission 5 --exit 70
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from database import get_db  # noqa: E402
import lay_draw_test as ldt  # noqa: E402

STAKE = 10.0


def load(conn=None):
    own = conn is None
    conn = conn or get_db()
    games = defaultdict(list)
    try:
        for row in conn.execute(
                """SELECT match_id, ts, inplay, minute, home_goals, away_goals, home_back, home_lay,
                          draw_back, draw_lay, away_back, away_lay
                   FROM inplay_prices ORDER BY match_id, ts"""):
            games[row[0]].append(dict(zip(("match_id", "ts", "inplay", "minute", "hg", "ag", "hb", "hl",
                                           "db", "dl", "ab", "al"), row)))
    except Exception:
        pass
    if own:
        conn.close()
    return games


def _mid(b, lay):
    return (b + lay) / 2 if b and lay else (b or lay)


def evaluate(snaps, exit_minute=70, commission=0.02):
    """One game's trade, or None if the log can't support it."""
    pre = [s for s in snaps if not s["inplay"] and s["dl"]]
    live = [s for s in snaps if s["inplay"] and s["hg"] is not None and s["ag"] is not None]
    if not pre or len(live) < 10:
        return None
    k = pre[-1]
    lay = k["dl"]
    odds = (_mid(k["hb"], k["hl"]), _mid(k["db"], k["dl"]), _mid(k["ab"], k["al"]))
    if not all(odds):
        return None
    ph, pd_, pa = ldt.market_fair(odds)
    lam = ldt.market_lambdas(ph, pd_, pa)
    final = live[-1]
    if (final["minute"] or 0) < 85:
        return None   # log stopped early: no reliable result
    is_draw = final["hg"] == final["ag"]
    hold = ldt.hold_pl(lay, is_draw, commission)

    first = next((i for i, s in enumerate(live) if (s["hg"] + s["ag"]) >= 1), None)
    out = {"lay": lay, "draw": int(is_draw), "hold": hold, "fav_home": ph >= pa}
    if first is not None and (live[first]["minute"] or 0) <= exit_minute:
        after = next((s for s in live[first + 1:] if s["db"]), None)
        if after is None:
            return None
        minute, lead = live[first]["minute"] or 0, (1 if live[first]["hg"] > live[first]["ag"] else -1)
        r = max(0.0, (90 - minute) / 90)
        expected = 1 / max(ldt.draw_prob(lam[0] * r, lam[1] * r, lead), 1e-6)
        back = after["db"]
        out.update(kind="goal", minute=minute, back=back, drift=back / expected,
                   scorer_fav=(lead == 1) == out["fav_home"])
    else:
        at = next((s for s in live if (s["minute"] or 0) >= exit_minute and s["db"]), None)
        if at is None:
            return None
        if (at["hg"] + at["ag"]) > 0:   # goal and exit landed in the same snapshot: skip
            return None
        out.update(kind="exit00", back=at["db"])
    green = STAKE - STAKE * lay / out["back"]
    out["trade"] = ldt._net(green, commission)
    return out


def summary(rows):
    if not rows:
        return None
    liab = sum(STAKE * (r["lay"] - 1) for r in rows)
    return {"n": len(rows), "trade": sum(r["trade"] for r in rows), "hold": sum(r["hold"] for r in rows),
            "trade_roi": sum(r["trade"] for r in rows) / liab, "hold_roi": sum(r["hold"] for r in rows) / liab,
            "drift": float(np.mean([r["drift"] for r in rows if "drift" in r])) if any("drift" in r for r in rows) else None}


def report(commission=0.02, exit_minute=70):
    games = load()
    rows = [r for r in (evaluate(s, exit_minute, commission) for s in games.values()) if r]
    print(f"In-play lay-the-draw with real Betfair prices: {len(games)} games logged, {len(rows)} usable "
          f"(£{STAKE:.0f} lay, {100 * commission:.0f}% commission, 0-0 exit at {exit_minute}')")
    if len(rows) < 30:
        print("  Not enough games yet. Give it a few weeks: a few hundred games before reading anything into it.")
        if not rows:
            return
    goal = [r for r in rows if r["kind"] == "goal"]
    groups = [
        ("All games", rows),
        ("Goal before exit", goal),
        ("0-0 at exit", [r for r in rows if r["kind"] == "exit00"]),
        ("Favourite scored first", [r for r in goal if r["scorer_fav"]]),
        ("Underdog scored first", [r for r in goal if not r["scorer_fav"]]),
        ("First goal 0-15'", [r for r in goal if r["minute"] <= 15]),
        ("First goal 16-30'", [r for r in goal if 16 <= r["minute"] <= 30]),
        ("First goal 31-45'", [r for r in goal if 31 <= r["minute"] <= 45]),
        ("First goal 46-70'", [r for r in goal if r["minute"] >= 46]),
    ]
    print("  group                    |    n | trade P/L (ROI)  | hold P/L (ROI)   | drift vs expected")
    for name, rs in groups:
        s = summary(rs)
        if not s:
            continue
        drift = f"{s['drift']:.3f}" if s["drift"] is not None else "  -"
        print(f"  {name:<24} | {s['n']:>4} | £{s['trade']:>6.0f} ({100 * s['trade_roi']:+5.1f}%) | "
              f"£{s['hold']:>6.0f} ({100 * s['hold_roi']:+5.1f}%) | {drift}")
    print("  ROI on liability. Drift above 1.00 = the draw drifted more after the goal than the kick-off")
    print("  prices implied. A real edge shows up as drift > 1 AND a positive trade ROI over hundreds of games.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commission", type=float, default=2.0)
    ap.add_argument("--exit", type=int, default=70)
    a = ap.parse_args()
    report(a.commission / 100, a.exit)


if __name__ == "__main__":
    main()
