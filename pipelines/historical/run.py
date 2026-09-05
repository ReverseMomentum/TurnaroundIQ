"""
Historical pipeline — CSVs -> historical_* tables -> team_stats profiles.

    python -u pipelines/historical/run.py
    python -u pipelines/historical/run.py --fetch --league "Premier League" --season 2024
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from progress import ok, step, warn

GINF = ROOT / "data" / "ginf.csv"
EVENTS = ROOT / "data" / "events.csv"


def run_script(script, extra=None):
    cmd = [sys.executable, "-u", str(ROOT / script)]
    if extra:
        cmd.extend(extra)
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Pull FBref CSVs first")
    parser.add_argument("--league")
    parser.add_argument("--season", type=int)
    args = parser.parse_args()

    started = time.time()
    if args.fetch or not GINF.exists() or not EVENTS.exists():
        extra = []
        if args.league:
            extra += ["--league", args.league]
        if args.season:
            extra += ["--season", str(args.season)]
        step("Fetch FBref source CSVs")
        run_script("training/fetch_fbref_source.py", extra)
    else:
        step("Using existing data/ginf.csv and data/events.csv")

    step("Import historical events")
    run_script("training/import_historical_events.py")

    step("Build historical team profiles")
    run_script("pipelines/historical/build.py")

    ok(f"Historical pipeline {round(time.time() - started, 1)}s")


if __name__ == "__main__":
    main()
