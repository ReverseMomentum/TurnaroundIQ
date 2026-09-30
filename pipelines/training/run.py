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

from progress import ok, step, warn
from database import get_db
from ops.backup import BackupError, backup_db


def run_script(script):
    result = subprocess.run(
        [sys.executable, "-u", str(ROOT / script)],
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
    step("Build training_data")
    run_script("training/build_training_data.py")
    conn = get_db()
    try:
        rows = conn.execute("SELECT COUNT(*) FROM training_data").fetchone()[0]
    finally:
        conn.close()
    if not rows:
        warn("training_data is empty — keeping the existing model; restore from backups/")
        raise SystemExit(1)
    ok(f"training_data rows: {rows}")
    step("Retrain model")
    run_script("models/retrain_model.py")
    ok(f"Training pipeline {round(time.time() - started, 1)}s")


if __name__ == "__main__":
    main()
