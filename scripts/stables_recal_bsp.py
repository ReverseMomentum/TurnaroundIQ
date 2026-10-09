#!/usr/bin/env python3
"""
The Stables: refit the place-chance calibration on recent races from Betfair's
daily BSP files, and put it live only if it beats the current one on the most
recent months (held back from the fit).

The learned model (scripts/stables_learn.py) trains on Kaggle races that stop
in 2020. The BSP files run to yesterday: win BSP for every runner (the same kind
of price the app works from) and who placed in Betfair's place market. That is
enough to re-learn how the engine's place chances line up with what happened,
by price and field size, on today's racing rather than 2008-2020's.

    scripts/cron_job.sh recal python -u scripts/stables_recal_bsp.py             # fit + score only
    scripts/cron_job.sh recal python -u scripts/stables_recal_bsp.py --save      # live if it scores better

Defaults: races from 2023-01-01 to yesterday, the last 3 months held back for
the test, up to 25,000 training races (random sample). Files are cached in
data/bsp/ (the history backfill already downloaded most of them).
"""
import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from racing import backtest, bsp_files, calibrate, nonfinish, positions, recalibrate, store  # noqa: E402
from racing.extra_place import ODDS_BANDS, band_label  # noqa: E402


def load(start: date, end: date) -> list[dict]:
    races, day = [], start
    while day <= end:
        for region in ("uk", "ire"):
            win, place = bsp_files.fetch(region, "win", day), bsp_files.fetch(region, "place", day)
            if win and place:
                for r in backtest.bsp_races(win, place):
                    r["day"] = bsp_files._date(r.get("event_dt")) or day.isoformat()
                    races.append(r)
        day += timedelta(days=1)
        if day.day == 1:
            print(f"  {day:%Y-%m}: {len(races)} races so far", flush=True)
    return races


def rows_for(races: list[dict], cal: dict, n_sims: int) -> dict:
    """Engine-style place chances (fitted curves, non-finish rates) vs who placed."""
    out = {k: [] for k in ("win_p", "win_y", "place_p", "place_win", "place_n", "place_y", "place_odds")}
    for race in races:
        p = np.asarray(race["p_win"], float)
        n = len(p)
        rtype = nonfinish.race_type(race.get("name"))
        odds = list(1 / p)
        sim = positions.simulate(p, n_sims=n_sims, discounts=calibrate.discounts_for(cal, rtype, n), seed=3,
                                 batches=2, dnf=nonfinish.rates_for(odds, rtype, cal.get("dnf")))
        k = int(race["places"])
        if k < 1 or k >= n:
            continue
        out["win_p"].extend(p)
        out["win_y"].extend(race["won"])
        out["place_p"].extend(sim["top"][:, k - 1])
        out["place_win"].extend(p)
        out["place_n"].extend([n] * n)
        out["place_y"].extend(race["placed"])
        out["place_odds"].extend(odds)
    return {k: np.asarray(v, float) for k, v in out.items()}


def log_loss(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def scored(rows: dict, recal) -> np.ndarray:
    if not recal or not recal.get("fitted"):
        return rows["place_p"]
    return recalibrate.calibrate_place(rows["place_p"], rows["place_win"], rows["place_n"], recal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--until", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    ap.add_argument("--test-months", type=int, default=3)
    ap.add_argument("--max-races", type=int, default=25000)
    ap.add_argument("--sims", type=int, default=1500)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    cal = store.latest_calibration()
    print(f"BSP races {a.since} to {a.until}", flush=True)
    races = load(a.since, a.until)
    if len(races) < 2000:
        print(f"only {len(races)} races with win + place files: not enough. Download failures:")
        for f in bsp_files.failures[:4]:
            print("  " + f)
        sys.exit(1)
    cut = (a.until - timedelta(days=30 * a.test_months)).isoformat()
    train = [r for r in races if r["day"] < cut]
    test = [r for r in races if r["day"] >= cut]
    random.Random(1).shuffle(train)
    train = train[:a.max_races]
    print(f"{len(races)} races: training on {len(train)} before {cut}, testing on {len(test)} after", flush=True)
    tr, te = rows_for(train, cal, a.sims), rows_for(test, cal, a.sims)
    new = recalibrate.fit(tr)
    if not new.get("fitted"):
        print("fit failed:", new)
        sys.exit(1)
    y = te["place_y"]
    current = cal.get("recal")
    scores = {"no calibration": log_loss(te["place_p"], y),
              "current (live)": log_loss(scored(te, current), y),
              "new (BSP)": log_loss(scored(te, new), y)}
    print(f"\nplace chance log loss on the last {a.test_months} months ({len(y)} runners; lower is better)")
    for k, v in scores.items():
        print(f"  {k:<16} {v:.5f}")
    print("\nplaced: predicted vs actual on the test months, by win price (BSP)")
    print(f"  {'odds':<10}{'runners':>8}{'actual':>8}{'raw':>8}{'live':>8}{'new':>8}")
    odds = te["place_odds"]
    bands = []
    for lo, hi in ODDS_BANDS:
        m = (odds >= lo) & (odds < hi)
        if m.sum() < 50:
            continue
        row = {"band": band_label(lo, hi), "n": int(m.sum()), "actual": float(y[m].mean()),
               "raw": float(te["place_p"][m].mean()), "live": float(scored(te, current)[m].mean()),
               "new": float(scored(te, new)[m].mean())}
        bands.append(row)
        print(f"  {row['band']:<10}{row['n']:>8}{100 * row['actual']:>7.1f}%{100 * row['raw']:>7.1f}%"
              f"{100 * row['live']:>7.1f}%{100 * row['new']:>7.1f}%")
    better = scores["new (BSP)"] < scores["current (live)"] - 1e-5
    print(f"\nnew calibration {'beats' if better else 'does not beat'} the live one on the test months")
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stables_recal_bsp.json").write_text(json.dumps(
        {"since": str(a.since), "until": str(a.until), "test_from": cut, "train_races": len(train),
         "test_races": len(test), "scores": scores, "bands": bands, "new": new, "better": better}, indent=1))
    if a.save and better:
        keep = {k: v for k, v in cal.items() if k not in ("created_at", "best_price_rate")}
        store.save_calibration({**keep, "recal": {**new, "source": f"bsp {a.since}..{a.until}"},
                                "recal_bsp_at": str(date.today())})
        print("saved: live from the next pricing")
    elif a.save:
        print("not saved: the live calibration scored as well or better")


if __name__ == "__main__":
    main()
