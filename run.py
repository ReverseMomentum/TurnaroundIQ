"""
TurnaroundIQ pipelines.

    python -u run.py live
    python -u run.py historical
    python -u run.py train
    python -u run.py live --skip-odds
    python -u run.py historical --league-id 39 --season 2024
    python -u run.py api              # restart API in tmux session "api"
    python -u run.py walk-forward     # chronological validation
    python -u run.py walk-forward --folds 5
    python -u run.py backup           # dated copy of two_up.db in backups/
    python -u run.py backup --list
    python -u run.py restore backups/two_up-YYYYMMDD-HHMMSS-label.db
    python -u run.py health           # row counts + freshness, non-zero exit if unhealthy
    python -u run.py restore-drill    # backup -> restore to scratch -> verify (live untouched)
"""

import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PIPELINES = {
    "live": ROOT / "pipelines" / "live" / "run.py",
    "historical": ROOT / "pipelines" / "historical" / "run.py",
    "train": ROOT / "pipelines" / "training" / "run.py",
    "training": ROOT / "pipelines" / "training" / "run.py",
}

API_COMMANDS = {"api", "api-restart", "restart-api"}
WALK_COMMANDS = {"walk-forward", "walkforward", "wf"}
COMPARE_COMMANDS = {"model-compare", "compare"}
USAGE = ("Usage: python -u run.py [live|historical|train|api|walk-forward|model-compare|"
         "backup|restore|restore-drill|health]")


def restart_api():
    script = ROOT / "scripts" / "restart_api.sh"
    if not script.is_file():
        print(f"Missing {script}")
        sys.exit(1)
    try:
        script.chmod(script.stat().st_mode | 0o111)
    except OSError:
        pass
    result = subprocess.run(["bash", str(script)], cwd=str(ROOT))
    sys.exit(result.returncode)


def run_walk_forward(command="walk-forward"):
    # FTA path model; the old conditional model: models/walk_forward.py
    script = ROOT / "models" / "fta_path_model.py"
    if not script.is_file():
        print(f"Missing {script}")
        sys.exit(1)
    # Pass through extra args after the command name
    extra = sys.argv[2:]
    result = subprocess.run(
        [sys.executable, "-u", str(script), command, *extra],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)


def main():
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "backup":
        from ops.backup import main as backup_main
        sys.exit(backup_main(sys.argv[2:]))
    if cmd == "restore":
        if len(sys.argv) < 3:
            print("Usage: python -u run.py restore <backup file>")
            sys.exit(1)
        from ops.backup import main as backup_main
        sys.exit(backup_main(["--restore", sys.argv[2]]))
    if cmd == "restore-drill":
        from ops.backup import main as backup_main
        sys.exit(backup_main(["--drill"]))
    if cmd == "health":
        from ops.health import main as health_main
        sys.exit(health_main())
    if cmd in API_COMMANDS:
        restart_api()
        return
    if cmd in WALK_COMMANDS:
        run_walk_forward()
        return
    if cmd in COMPARE_COMMANDS:
        run_walk_forward("compare")
        return
    if cmd not in PIPELINES:
        print(USAGE)
        sys.exit(1)
    target = PIPELINES[cmd]
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
