#!/usr/bin/env python3
"""
The Stables: load Kaggle results into rac_history (run once), so live runners
get course / distance / jockey / trainer place rates from day one. Our own
Betfair results are added automatically by the collector after each race.

    venv/bin/python -u scripts/stables_history.py data/kaggle/hwaitt            # 2015 onwards
    venv/bin/python -u scripts/stables_history.py data/kaggle/hwaitt --since 2012
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from racing import live_features  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--since", type=int, default=2015)
    a = ap.parse_args()
    print("reading Kaggle files...", flush=True)
    live_features.history_from_kaggle(a.paths, a.since, log=lambda m: print(m, flush=True))
    print(f"rac_history: done ({a.since}+)", flush=True)


if __name__ == "__main__":
    main()
