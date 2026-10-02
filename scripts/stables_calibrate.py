#!/usr/bin/env python3
"""
The Stables: fit the position discounts (and the form blend, once there are
enough races with features) on every race with a result, score prior vs fitted
on the latest 25% of races, and save the fit for the app.

    venv/bin/python scripts/stables_calibrate.py            # fit, score, save
    venv/bin/python scripts/stables_calibrate.py --dry-run  # fit and score only
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402

from racing import calibrate, market, positions, store  # noqa: E402


def main():
    dry = "--dry-run" in sys.argv
    rows = store.races_with_results()
    races = []
    for row in sorted(rows, key=lambda x: (x["race"].get("date") or "", x["race"].get("time") or "")):
        runners = row["race"]["runners"]
        if len(runners) < 2 or not row["order"]:
            continue
        p, _, _ = market.fair_win_probs(runners)
        feats = np.array([[(r.get("features") or {}).get(f, np.nan) for f in store.FEATURE_COLS]
                          for r in runners], float)
        races.append({"p_win": p, "order": row["order"],
                      "features": feats if np.isfinite(feats).any() else None})
    print(f"races with results: {len(races)}")
    if not races:
        return
    cut = int(len(races) * 0.75)
    train, test = races[:cut] or races, races[cut:] or races
    fit = calibrate.fit_discounts(train)
    print("discounts:", json.dumps(fit))
    blend = calibrate.fit_blend(train, store.FEATURE_COLS)
    print("form blend:", json.dumps({k: v for k, v in blend.items() if k != "weights"}))
    prior = calibrate.evaluate(test, positions.DEFAULT_DISCOUNTS)
    fitted = calibrate.evaluate(test, fit["discounts"]) if fit["fitted"] else None
    print(f"held-back races: {len(test)}")
    for key in ("top1", "top3", "top4", "top5", "top6", "extra3to4", "extra3to5"):
        if key in prior:
            line = f"  {key:<10} prior brier {prior[key]['brier']:.5f} ece {prior[key]['calibration_error']:.4f}"
            if fitted and key in fitted:
                line += f" | fitted brier {fitted[key]['brier']:.5f} ece {fitted[key]['calibration_error']:.4f}"
            print(line)
    if dry or not fit["fitted"]:
        print("not saved" + ("" if dry else f" ({fit.get('reason')})"))
        return
    # Refit on everything for the saved version.
    full = calibrate.fit_discounts(races)
    store.save_calibration({**full, "blend": calibrate.fit_blend(races, store.FEATURE_COLS),
                            "held_back": {"prior": prior, "fitted": fitted}})
    print("saved")


if __name__ == "__main__":
    main()
