"""
Training pipeline — FTA path model (V5).

    python -u run.py train             # backup, then fit fta_path_model.pkl
    python -u run.py train --legacy    # also rebuild the old fta_model.pkl
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from progress import ok, step, warn
from ops.backup import BackupError, backup_db


def run_script(script, extra=None):
    result = subprocess.run(
        [sys.executable, "-u", str(ROOT / script), *(extra or [])],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    started = time.time()
    step("Back up two_up.db")
    try:
        backup_db("pre-train")
    except BackupError as exc:
        warn(f"Backup failed ({exc}) — not training without a backup")
        raise SystemExit(1)
    step("Train FTA path model (V5: P(2-up) x P(fail | 2-up), point-in-time)")
    run_script("models/fta_path_model.py", ["train"])
    if "--legacy" in sys.argv:
        step("Legacy: build training_data + retrain fta_model.pkl")
        run_script("training/build_training_data.py")
        run_script("models/retrain_model.py")
    ok(f"Training pipeline {round(time.time() - started, 1)}s")


if __name__ == "__main__":
    main()
