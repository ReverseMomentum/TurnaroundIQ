#!/usr/bin/env python3
"""
The Stables: free date-split test on Kaggle results.

Fits the position discounts on races up to --train-to, then on races from
--test-from onwards (never seen in fitting) scores published-prior vs fitted
discounts (Brier, log loss, calibration error for top 1/3/4/5/6 and the extra
places) and runs a paper each-way backtest with 1 and 2 extra places.

Download (one line, needs ~/.kaggle/kaggle.json):
    venv/bin/pip install -q kaggle && venv/bin/kaggle datasets download -d hwaitt/horse-racing -p data/kaggle/hwaitt --unzip

Run:
    venv/bin/python scripts/stables_kaggle_check.py data/kaggle/hwaitt --peek
    venv/bin/python scripts/stables_kaggle_check.py data/kaggle/hwaitt --train-to 2017 --test-from 2018
    venv/bin/python scripts/stables_kaggle_check.py data/kaggle/hwaitt --train-to 2017 --test-from 2018 --save

--save stores discounts refitted on train + test for the app (grade A unlocks).
Output is also written to logs/stables_kaggle_check.json.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from racing import backtest, calibrate, datasets, positions, store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--peek", action="store_true", help="show columns and how they were matched, then stop")
    ap.add_argument("--train-from", type=int, default=2005)
    ap.add_argument("--train-to", type=int, default=2017)
    ap.add_argument("--test-from", type=int, default=2018)
    ap.add_argument("--test-to", type=int, default=2100)
    ap.add_argument("--max-train", type=int, default=20000, help="random sample of training races")
    ap.add_argument("--max-test", type=int, default=5000, help="random sample of test races")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    if a.peek:
        print(datasets.peek(a.paths))
        return
    t0 = time.time()
    rng = random.Random(1)
    train = datasets.load_races(a.paths, years=(a.train_from, a.train_to))
    test = datasets.load_races(a.paths, years=(a.test_from, a.test_to))
    print(f"loaded {len(train)} train races ({a.train_from}-{a.train_to}), {len(test)} test races "
          f"({a.test_from}+) in {time.time() - t0:.0f}s")
    if not train or not test:
        print("nothing to test: check the paths and years (try --peek)")
        sys.exit(1)
    train_s = rng.sample(train, min(len(train), a.max_train))
    test_s = sorted(rng.sample(test, min(len(test), a.max_test)), key=lambda r: r["date"])

    fit = calibrate.fit_discounts(backtest.to_calibration_races(train_s))
    print("prior discounts :", list(positions.DEFAULT_DISCOUNTS))
    print("fitted discounts:", fit["discounts"], f"(train NLL {fit.get('nll_prior')} -> {fit.get('nll_fitted')})")

    test_cal = backtest.to_calibration_races(test_s)
    prior = calibrate.evaluate(test_cal, positions.DEFAULT_DISCOUNTS, n_sims=2000)
    fitted = calibrate.evaluate(test_cal, fit["discounts"], n_sims=2000)
    print(f"\nheld-back test, {len(test_s)} races (lower is better)")
    print(f"  {'':<10}{'prior brier':>12}{'fitted':>9}{'prior ECE':>11}{'fitted':>9}{'predicted':>11}{'actual':>8}")
    for key in ("top1", "top3", "top4", "top5", "top6", "extra3to4", "extra3to5"):
        if key in prior:
            p, f = prior[key], fitted[key]
            print(f"  {key:<10}{p['brier']:>12.5f}{f['brier']:>9.5f}{p['calibration_error']:>11.4f}"
                  f"{f['calibration_error']:>9.4f}{f['mean_predicted']:>11.4f}{f['observed_rate']:>8.4f}")

    cal = {**fit, "n_races": fit["n_races"]}
    bt = {}
    for extra in (1, 2):
        bt[extra] = backtest.ew_backtest(test_s, cal, extra=extra)
        print(f"\npaper each-way at SP, standard places + {extra}, {bt[extra]['races']} races (8+ runners)")
        for g in ("A", "B", "other"):
            s = bt[extra].get(g)
            if s:
                print(f"  grade {g:<6} bets {s['bets']:>6}  model EV {100 * s['mean_model_ev']:+6.1f}%  "
                      f"actual ROI {100 * s['roi']:+6.1f}%  placed {s['placed']:>5}  via extra places {s['extra_place_hits']:>4}")
    print("\nSP has more margin than early prices; dead heats and Rule 4 ignored. Illustrative only.")

    out = {"train_races": len(train_s), "test_races": len(test_s), "fit": fit,
           "test_prior": prior, "test_fitted": fitted, "ew_backtest": bt}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stables_kaggle_check.json").write_text(json.dumps(out, indent=1, default=str))
    if a.save:
        full = calibrate.fit_discounts(backtest.to_calibration_races(rng.sample(train + test, min(len(train) + len(test), a.max_train))))
        store.save_calibration({**full, "source": "kaggle", "held_back": {"prior": prior, "fitted": fitted}})
        print("saved discounts for the app:", full["discounts"])


if __name__ == "__main__":
    main()
