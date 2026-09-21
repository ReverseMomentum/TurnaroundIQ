"""
TurnaroundIQ pipelines.

    python -u run.py live
    python -u run.py historical
    python -u run.py train
    python -u run.py live --skip-odds
    python -u run.py historical --fetch --league "Premier League" --season 2024
    python -u run.py api          # restart API in tmux session "api"
    python -u run.py api-restart  # same
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


def restart_api():
    script = ROOT / "scripts" / "restart_api.sh"
    if not script.is_file():
        print(f"Missing {script}")
        sys.exit(1)
    # Ensure executable bit for direct bash invoke
    try:
        script.chmod(script.stat().st_mode | 0o111)
    except OSError:
        pass
    result = subprocess.run(["bash", str(script)], cwd=str(ROOT))
    sys.exit(result.returncode)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -u run.py [live|historical|train|api]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd in API_COMMANDS:
        restart_api()
        return
    if cmd not in PIPELINES:
        print("Usage: python -u run.py [live|historical|train|api]")
        sys.exit(1)
    target = PIPELINES[cmd]
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
