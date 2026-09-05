"""
Live pipeline — results, team_stats, xG, odds.
Does not rebuild training_data.

    python -u pipelines/live/run.py
    python -u pipelines/live/run.py --skip-odds --skip-xg
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from progress import ProgressBar, ok, step, warn

STEPS = [
    ("Collect finished results", "collectors/results_collector.py", "always"),
    ("Update live team stats", "pipelines/live/team_stats.py", "always"),
    ("Update live + divergence stats", "training/update_live_team_stats.py", "always"),
    ("Update xG / last-5 form", "collectors/xg_collector.py", "xg"),
    ("Refresh live odds", "collectors/odds_collector.py", "odds"),
    ("Backfill CSV odds", "collectors/odds_football_data.py", "odds"),
]


def run_script(script):
    return subprocess.run(
        [sys.executable, "-u", str(ROOT / script)],
        cwd=str(ROOT),
    ).returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-odds", action="store_true")
    parser.add_argument("--skip-xg", action="store_true")
    args = parser.parse_args()

    jobs = []
    for name, script, kind in STEPS:
        if kind == "odds" and args.skip_odds:
            continue
        if kind == "xg" and args.skip_xg:
            continue
        jobs.append((name, script))

    bar = ProgressBar(len(jobs), label="Live")
    failed = 0
    started = time.time()
    for name, script in jobs:
        step(name)
        t0 = time.time()
        code = run_script(script)
        if code != 0:
            warn(f"{name} exited {code} after {round(time.time() - t0, 1)}s")
            failed += 1
        else:
            ok(f"{name} {round(time.time() - t0, 1)}s")
        bar.update(detail=name)
    bar.finish()
    ok(f"Live pipeline {round(time.time() - started, 1)}s")
    if failed:
        warn(f"{failed} step(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
