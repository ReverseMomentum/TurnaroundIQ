"""
Refresh data used by opportunities_engine.

Does NOT rebuild training_data or retrain fta_model.pkl.
Run this when you want an updated opportunity list.

Usage:
    python refresh_live.py
    python refresh_live.py --skip-odds
    python refresh_live.py --skip-xg
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def run_step(name, script):

    print("\n" + "=" * 70)
    print(f"Running: {name}")
    print("=" * 70)

    start = time.time()

    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / script)],
        check=True,
        cwd=str(PROJECT_ROOT),
    )

    runtime = round(time.time() - start, 1)
    print(f"\nCompleted: {name} ({runtime}s)")


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Refresh match results, team_stats and odds "
            "for the opportunities engine."
        )
    )
    parser.add_argument(
        "--skip-odds",
        action="store_true",
        help="Do not run odds_collector.py",
    )
    parser.add_argument(
        "--skip-xg",
        action="store_true",
        help="Do not run xg_collector.py",
    )
    args = parser.parse_args()

    steps = [
        ("Collect finished results", "collectors/results_collector.py"),
        ("Update team profiles", "collectors/update_team_profiles.py"),
        ("Update turnaround stats", "collectors/update_turnaround_stats.py"),
        ("Update live + divergence stats", "training/update_live_team_stats.py"),
    ]

    if not args.skip_xg:
        steps.append(
            ("Update xG / last-5 form", "collectors/xg_collector.py")
        )

    if not args.skip_odds:
        steps.append(
            ("Refresh odds", "collectors/odds_collector.py")
        )

    overall_start = time.time()

    print("\n" + "=" * 70)
    print("TURNAROUND IQ - LIVE REFRESH")
    print("=" * 70)

    for name, script in steps:
        run_step(name, script)

    total_runtime = round(time.time() - overall_start, 1)

    print("\n" + "=" * 70)
    print("LIVE REFRESH COMPLETE")
    print("=" * 70)
    print(f"Total runtime: {total_runtime}s")
    print("Reload the Opportunities tab.")
    print("Training / model were not touched.")


if __name__ == "__main__":
    main()
