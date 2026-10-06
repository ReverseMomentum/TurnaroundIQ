#!/usr/bin/env python3
"""
The Stables: typical bookmaker book by field size, from Kaggle starting prices.

Races with no bookmaker price are graded at an estimated bookmaker price: the
exchange's fair chances inflated to this book (racing/market.py). Until this
runs, the engine uses ~1 + 1.8% a runner. SP books are a little bigger than
early prices, so the estimate leans cautious.

    venv/bin/python -u scripts/stables_overround.py data/kaggle/hwaitt            # 2015 onwards, saves
    venv/bin/python -u scripts/stables_overround.py data/kaggle/hwaitt --dry-run
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from racing import datasets, market, store  # noqa: E402


def fit(races, min_races: int = 30) -> dict:
    by_n = defaultdict(list)
    for r in races:
        odds = [x["odds"] for x in r["runners"]]
        if len(odds) >= 2 and all(o and o > 1 for o in odds):
            by_n[len(odds)].append(sum(1 / o for o in odds))
    return {str(n): round(float(np.median(v)), 4) for n, v in sorted(by_n.items()) if len(v) >= min_races}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--since", type=int, default=2015)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    table = fit(datasets.load_races(a.paths, years=(a.since, 2100)))
    for n, v in table.items():
        print(f"  {n:>2} runners: book {100 * v:.1f}%   (rule of thumb {100 * market.typical_overround(int(n)):.1f}%)")
    if not table:
        print("no races with complete starting prices")
        sys.exit(1)
    if not a.dry_run:
        store.save_calibration({**store.latest_calibration(), "book_overround": table})
        print("saved for the app (restart the API to use it)")


if __name__ == "__main__":
    main()
