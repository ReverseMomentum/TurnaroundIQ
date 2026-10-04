#!/usr/bin/env python3
"""
The Stables: learn runner features on Kaggle history and test them on later years.

  1. Builds point-in-time features for every runner (racing/features.py)
  2. Picks feature groups on validation years (kept only if they help)
  3. Fits the ranking model on the first six finishers (racing/learn.py)
  4. On test years, compares it with the current model: finishing-order loss,
     top-3 / top-5 / extra-place calibration, and a paper each-way backtest
  5. Logs the run in model_runs; --save puts it live (with a calibration refit)

    venv/bin/python -u scripts/stables_learn.py data/kaggle/hwaitt
    venv/bin/python -u scripts/stables_learn.py data/kaggle/hwaitt --save

Defaults: train 2008-2015, validate 2016-2017, test 2018+, fields of 8+ runners
(--min-runners). About 20-30 minutes.
Writes logs/stables_learn.json.
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from database import get_db  # noqa: E402
from racing import (backtest, calibrate, datasets, features, learn, nonfinish, positions,  # noqa: E402
                    recalibrate, store)


def _table(title, rows):
    print(f"\n{title}")
    print(f"  {'':<14}{'bets':>6}{'model':>8}{'actual':>8}")
    for label, r in rows.items():
        if r.get("bets"):
            print(f"  {label:<14}{r['bets']:>6}{100 * r['model_ev']:>+7.1f}%{100 * r['roi']:>+7.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--train-from", type=int, default=2008)
    ap.add_argument("--train-to", type=int, default=2015)
    ap.add_argument("--valid-to", type=int, default=2017)
    ap.add_argument("--test-from", type=int, default=2018)
    ap.add_argument("--max-train", type=int, default=30000)
    ap.add_argument("--max-valid", type=int, default=8000)
    ap.add_argument("--max-test", type=int, default=5000)
    ap.add_argument("--recal-races", type=int, default=4000)
    ap.add_argument("--min-runners", type=int, default=8,
                    help="train / test only on fields this big (extra places are rarely offered below 8)")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    rng = random.Random(3)

    every = datasets.load_races(a.paths, years=(a.train_from, 2100))
    print(f"loaded {len(every)} races in {time.time() - t0:.0f}s", flush=True)
    feats = features.training_features(a.paths, (a.train_from, 2100))
    n = features.attach(every, feats)
    total = sum(len(r["runners"]) for r in every)
    print(f"features for {n}/{total} runners in {time.time() - t0:.0f}s", flush=True)

    year = lambda r: int(r["date"][:4])  # noqa: E731
    # Features above used every race (a small-field run is still form); the model is
    # fitted and tested only on fields where bookmakers pay extra places.
    every = [r for r in every if len(r["runners"]) >= a.min_runners]
    print(f"{len(every)} races with {a.min_runners}+ runners", flush=True)
    train = [r for r in every if year(r) <= a.train_to]
    valid = [r for r in every if a.train_to < year(r) <= a.valid_to]
    test = [r for r in every if year(r) >= a.test_from]
    train_s = rng.sample(train, min(len(train), a.max_train))
    valid_s = rng.sample(valid, min(len(valid), a.max_valid))
    test_s = sorted(rng.sample(test, min(len(test), a.max_test)), key=lambda r: r["date"])
    print(f"train {len(train_s)} / validate {len(valid_s)} / test {len(test_s)} races")

    base = store.latest_calibration()
    disc = base.get("discounts") if base.get("fitted") else None
    if not disc:
        disc = calibrate.fit_discounts(backtest.to_calibration_races(train_s))["discounts"]
    dnf = base.get("dnf") or nonfinish.fit_rates(train)
    print("position discounts:", disc)

    print("\nfeature groups (kept only if validation loss falls):")
    sel = learn.select(train_s, valid_s, disc)
    blend = learn.fit(train_s + valid_s, sel["features"], disc)
    print("\nlearned weights (per standard deviation; + = runs better than its price):")
    print(f"  {'market (log p)':<20}{blend['weights'][0]:+.3f}")
    for name, w in learn.importance(blend):
        print(f"  {name:<20}{w:+.3f}")

    print(f"\ntest races {a.test_from}+ (lower is better)")
    lm, ll = learn.loss(test_s, None, disc), learn.loss(test_s, blend, disc)
    print(f"  finishing-order loss: market {lm:.5f}  learned {ll:.5f}  ({100 * (lm - ll) / lm:+.2f}%)")
    ev_m = calibrate.evaluate(backtest.to_calibration_races(test_s, dnf), disc, n_sims=2000)
    ev_l = calibrate.evaluate(backtest.to_calibration_races(test_s, dnf, blend), disc, n_sims=2000)
    print(f"  {'':<11}{'brier mkt':>10}{'learned':>9}{'ECE mkt':>9}{'learned':>9}{'actual':>8}")
    for key in ("top1", "top3", "top4", "top5", "top6", "extra3to5"):
        if key in ev_m:
            print(f"  {key:<11}{ev_m[key]['brier']:>10.5f}{ev_l[key]['brier']:>9.5f}"
                  f"{ev_m[key]['calibration_error']:>9.4f}{ev_l[key]['calibration_error']:>9.4f}"
                  f"{ev_m[key]['observed_rate']:>8.3f}")

    recal_races = rng.sample(train + valid, min(len(train) + len(valid), a.recal_races))
    cal_m = {"discounts": disc, "fitted": True, "n_races": len(train_s), "dnf": dnf,
             "recal": base.get("recal") or recalibrate.fit(recalibrate.build_rows(recal_races, {"discounts": disc, "dnf": dnf}))}
    cal_l = {**cal_m, "blend": blend}
    cal_l["recal"] = recalibrate.fit(recalibrate.build_rows(recal_races, {**cal_l, "recal": None}))
    print("\ncalibration refitted on the learned model:", cal_l["recal"].get("fitted"), flush=True)

    bt = {}
    for label, cal in (("current", cal_m), ("learned", cal_l)):
        bt[label] = backtest.ew_backtest(test_s, cal, extra=1, min_runners=a.min_runners)
        print(f"\n=== paper each-way, places +1, {bt[label]['races']} test races: {label} model ===")
        _table("by grade", bt[label]["by_grade"])
        _table("by model EV", bt[label]["by_ev"])
        _table("by win odds", bt[label]["by_odds"])
    print("\nSP prices; dead heats and Rule 4 ignored. Illustrative only.")

    out = {"selection": sel, "blend": blend, "test_loss": {"market": lm, "learned": ll},
           "test_eval": {"market": ev_m, "learned": ev_l}, "backtest": bt,
           "races": {"train": len(train_s), "valid": len(valid_s), "test": len(test_s)},
           "min_runners": a.min_runners}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stables_learn.json").write_text(json.dumps(out, indent=1, default=str))
    conn = get_db()
    try:
        conn.execute("INSERT INTO model_runs (model_name, version, trained_at, training_rows, brier_score, log_loss, notes) "
                     "VALUES (?,?,?,?,?,?,?)",
                     ("stables_learned", datetime.now(timezone.utc).strftime("%Y%m%d%H%M"),
                      datetime.now(timezone.utc).isoformat(timespec="seconds"), len(train_s) + len(valid_s),
                      ev_l.get("top5", {}).get("brier"), ll,
                      f"features={','.join(sel['features']) or 'none'}; market_loss={lm:.5f}; "
                      f"min_runners={a.min_runners}; saved={a.save}"))
        conn.commit()
    except Exception as e:  # model_runs is optional
        print("model_runs not written:", e)
    finally:
        conn.close()
    if a.save:
        if ll >= lm:
            print("\nnot saved: the learned model did not beat the market on test races")
            return
        store.save_calibration({**base, **cal_l, "source": "kaggle+learned", "min_runners": a.min_runners,
                                "learned_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print("\nsaved for the app: features", sel["features"])


if __name__ == "__main__":
    main()
