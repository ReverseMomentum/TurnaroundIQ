"""
TurnaroundIQ pipelines.

    python -u run.py live
    python -u run.py historical
    python -u run.py train
    python -u run.py live --skip-odds
    python -u run.py historical --fetch --league "Premier League" --season 2024
"""

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PIPELINES = {
    "live": ROOT / "pipelines" / "live" / "run.py",
    "historical": ROOT / "pipelines" / "historical" / "run.py",
    "train": ROOT / "pipelines" / "training" / "run.py",
    "training": ROOT / "pipelines" / "training" / "run.py",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in PIPELINES:
        print("Usage: python -u run.py [live|historical|train]")
        sys.exit(1)
    target = PIPELINES[sys.argv[1]]
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
