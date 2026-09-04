"""
Refresh data used by opportunities_engine.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from progress import ProgressBar, ok, step, warn


def run_step(name, script, bar):
    step(name)
    start = time.time()
    result = subprocess.run(
        [sys.executable, "-u", str(PROJECT_ROOT / script)],
        cwd=str(PROJECT_ROOT),
    )
    runtime = round(time.time() - start, 1)
    if result.returncode != 0:
        warn(f"{name} exited {result.returncode} after {runtime}s")
        bar.update(detail=name)
        return False
    ok(f"{name} finished in {runtime}s")
    bar.update(detail=name)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Refresh match results, team_stats and odds."
    )
    parser.add_argument("--skip-odds", action="store_true")
    parser.add_argument("--skip-xg", action="store_true")
    args = parser.parse_args()

    steps = [
        ("Collect finished results", "collectors/results_collector.py"),
        ("Update team profiles", "collectors/update_team_profiles.py"),
        ("Update turnaround stats", "collectors/update_turnaround_stats.py"),
        ("Update live + divergence stats", "training/update_live_team_stats.py"),
    ]
    if not args.skip_xg:
        steps.append(("Update xG / last-5 form", "collectors/xg_collector.py"))
    if not args.skip_odds:
        steps.append(("Refresh live odds", "collectors/odds_collector.py"))
        steps.append(("Backfill CSV odds", "collectors/odds_football_data.py"))

    bar = ProgressBar(len(steps), label="Refresh")
    failed = 0
    started = time.time()
    for name, script in steps:
        if not run_step(name, script, bar):
            failed += 1
    bar.finish()
    ok(f"Live refresh finished in {round(time.time() - started, 1)}s")
    if failed:
        warn(f"{failed} step(s) failed")
    else:
        ok("Reload the Opportunities tab. Training was not touched.")


if __name__ == "__main__":
    main()
