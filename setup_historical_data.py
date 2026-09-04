"""
Historical pipeline. Do not bypass these scripts.

1. Fetch FBref into data/ginf.csv + data/events.csv (if missing)
2. Import those files into historical_matches / historical_events
3. build_historical_team_intelligence.py
4. build_historical_advanced_features.py
"""

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
GINF = PROJECT_ROOT / "data" / "ginf.csv"
EVENTS = PROJECT_ROOT / "data" / "events.csv"


def run_step(name, script, extra_args=None):
    print("\n" + "=" * 70)
    print(f"Running: {name}")
    print("=" * 70)
    start = time.time()
    cmd = [sys.executable, "-u", script]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
    print(f"\nCompleted: {name} ({round(time.time() - start, 1)}s)")


def main():
    steps = []
    if not GINF.exists() or not EVENTS.exists():
        steps.append(
            ("Fetch FBref source CSVs", "training/fetch_fbref_source.py", None)
        )
    steps.extend(
        [
            ("Import Historical Events", "training/import_historical_events.py", None),
            (
                "Build Historical Team Intelligence",
                "training/build_historical_team_intelligence.py",
                None,
            ),
            (
                "Build Historical Advanced Features",
                "training/build_historical_advanced_features.py",
                None,
            ),
        ]
    )

    print("\n" + "=" * 70)
    print("TURNAROUND IQ - HISTORICAL SETUP")
    print("=" * 70)
    started = time.time()
    for name, script, extra in steps:
        run_step(name, script, extra)
    print("\n" + "=" * 70)
    print("HISTORICAL SETUP COMPLETE")
    print("=" * 70)
    print(f"Total Runtime: {round(time.time() - started, 1)}s")
    print("historical_matches + historical_events ready for team profiles.")


if __name__ == "__main__":
    main()
