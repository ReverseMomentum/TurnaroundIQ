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

--save stores, for the app: discounts and non-finish rates refitted on train +
test, and the win/place calibration fitted on training races (grade A unlocks).
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
from racing import backtest, calibrate, datasets, nonfinish, positions, recalibrate, store  # noqa: E402


def _table(title, rows):
    print(f"\n{title}")
    print(f"  {'':<14}{'bets':>6}{'model':>8}{'actual':>8}")
    for label, r in rows.items():
        if r.get("bets"):
            print(f"  {label:<14}{r['bets']:>6}{100 * r['model_ev']:>+7.1f}%{100 * r['roi']:>+7.1f}%")


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
    ap.add_argument("--recal-races", type=int, default=5000, help="training races used to fit the calibration")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    if a.peek:
        print(datasets.peek(a.paths))
        return
    t0 = time.time()
    rng = random.Random(1)
    every = datasets.load_races(a.paths, years=(a.train_from, a.test_to))
    train = [r for r in every if int(r["date"][:4]) <= a.train_to]
    test = [r for r in every if int(r["date"][:4]) >= a.test_from]
    print(f"loaded {len(train)} train races ({a.train_from}-{a.train_to}), {len(test)} test ({a.test_from}+) "
          f"in {time.time() - t0:.0f}s", flush=True)
    if not train or not test:
        print("nothing to test: check the paths and years (try --peek)")
        sys.exit(1)
    train_s = rng.sample(train, min(len(train), a.max_train))
    test_s = sorted(rng.sample(test, min(len(test), a.max_test)), key=lambda r: r["date"])

    dnf = nonfinish.fit_rates(train)
    print("\nnon-finish rates by price band (<5, 5-10, 10-20, 20-50, 50+):")
    for t in ("flat", "hurdle", "chase"):
        print(f"  {t:<7}" + " ".join(f"{100 * x:4.1f}%" for x in dnf[t]) + f"  ({dnf['runners'][t]} runners)")

    fit = calibrate.fit_discounts(backtest.to_calibration_races(train_s))
    print("\nprior discounts :", list(positions.DEFAULT_DISCOUNTS))
    print("fitted discounts:", fit["discounts"], flush=True)
    cal = {**fit, "dnf": dnf}

    recal_races = rng.sample(train, min(len(train), a.recal_races))
    recal = recalibrate.fit(recalibrate.build_rows(recal_races, cal))
    print(f"\ncalibration (fitted on {len(recal_races)} training races): {recal}", flush=True)
    cal["recal"] = recal

    rep = recalibrate.report(recalibrate.build_rows(test_s, cal), recal)
    print(f"\nplace chance on test races, raw vs calibrated (ECE lower is better)")
    print(f"  {'odds':<8}{'runners':>8}{'actual':>8}{'raw':>7}{'cal':>7}{'rawECE':>8}{'calECE':>8}")
    for band, r in rep.items():
        print(f"  {band:<8}{r['n']:>8}{r['actual']:>8.3f}{r['raw']:>7.3f}{r['calibrated']:>7.3f}"
              f"{r['raw_ece']:>8.4f}{r['cal_ece']:>8.4f}")

    test_plain = backtest.to_calibration_races(test_s)
    test_dnf = backtest.to_calibration_races(test_s, dnf)
    scores = {"prior": calibrate.evaluate(test_plain, positions.DEFAULT_DISCOUNTS, n_sims=2000),
              "prior+dnf": calibrate.evaluate(test_dnf, positions.DEFAULT_DISCOUNTS, n_sims=2000),
              "fitted+dnf": calibrate.evaluate(test_dnf, fit["discounts"], n_sims=2000)}
    print(f"\nheld-back test, {len(test_s)} races")
    print("calibration error (lower is better)")
    print(f"  {'':<10}" + "".join(f"{k:>11}" for k in scores) + f"{'actual':>8}")
    for key in ("top1", "top3", "top4", "top5", "top6", "extra3to4", "extra3to5"):
        if key in scores["prior"]:
            print(f"  {key:<10}" + "".join(f"{v[key]['calibration_error']:>11.4f}" for v in scores.values())
                  + f"{scores['prior'][key]['observed_rate']:>8.3f}")
    print("brier (lower is better)")
    for key in ("top3", "top5", "extra3to5"):
        print(f"  {key:<10}" + "".join(f"{v[key]['brier']:>11.5f}" for v in scores.values()))

    bt = {}
    for extra in (1, 2):
        bt[extra] = backtest.ew_backtest(test_s, cal, extra=extra)
        print(f"\n=== paper each-way, places +{extra}, {bt[extra]['races']} test races ===", flush=True)
        _table("by grade", bt[extra]["by_grade"])
        _table("by model EV", bt[extra]["by_ev"])
        _table("by win odds", bt[extra]["by_odds"])
        _table("by race type", bt[extra]["by_type"])
    print("\nmodel = EV the page would show; actual = paper ROI at SP.")
    print("Dead heats and Rule 4 ignored. Illustrative only.")

    out = {"train_races": len(train_s), "test_races": len(test_s), "fit": fit, "dnf": dnf,
           "recal": recal, "recal_report": rep, "test_scores": scores, "ew_backtest": bt}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stables_kaggle_check.json").write_text(json.dumps(out, indent=1, default=str))
    if a.save:
        full = calibrate.fit_discounts(backtest.to_calibration_races(
            rng.sample(every, min(len(every), a.max_train))))
        payload = {**full, "dnf": nonfinish.fit_rates(every), "recal": recal,
                   "source": "kaggle", "held_back": scores}
        store.save_calibration(payload)
        print("saved for the app:", full["discounts"], "calibration", recal.get("fitted"))


if __name__ == "__main__":
    main()
