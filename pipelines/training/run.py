"""
Training pipeline — labelled rows then model fit.

    python -u pipelines/training/run.py
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from progress import ok, step


def run_script(script):
    result = subprocess.run(
        [sys.executable, "-u", str(ROOT / script)],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    started = time.time()
    step("Build training_data")
    run_script("training/build_training_data.py")
    step("Retrain model")
    run_script("models/retrain_model.py")
    ok(f"Training pipeline {round(time.time() - started, 1)}s")


if __name__ == "__main__":
    main()
