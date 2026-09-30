"""
two_up.db backups — consistent online copies via SQLite's backup API.

    python -u run.py backup                 # manual backup
    python -u run.py backup --list          # show backups + row counts
    python -u run.py restore <file>         # restore (stop the API first)

Env:
  BACKUP_DIR    default <repo>/backups
  BACKUP_KEEP   how many backups to keep (default 30)

Pipelines call backup_db(label) before destructive steps (train, historical,
results --force) and after a successful live run. A backup that looks empty
never triggers pruning, so a wiped DB cannot rotate out the good copies.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import DB_NAME

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", str(ROOT / "backups")))
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "30"))
CORE_TABLES = ("match_results", "team_stats", "training_data")


class BackupError(RuntimeError):
    pass


def row_counts(path) -> dict:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            t: (conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                if t in tables else None)
            for t in CORE_TABLES
        }
    finally:
        conn.close()


def _looks_empty(counts: dict) -> bool:
    return not counts.get("match_results")


def _integrity_ok(path) -> bool:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def _copy(src, dst):
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(str(dst))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def list_backups():
    if not BACKUP_DIR.is_dir():
        return []
    return sorted(BACKUP_DIR.glob("two_up-*.db"))


def prune(keep=BACKUP_KEEP):
    files = list_backups()
    removed = []
    for old in files[:-keep] if keep > 0 else []:
        old.unlink()
        removed.append(old)
    return removed


def backup_db(label="manual") -> Path:
    """Copy the live DB to BACKUP_DIR. Raises BackupError on failure."""
    src = Path(DB_NAME)
    if not src.is_file():
        raise BackupError(f"DB not found: {src}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
    dst = BACKUP_DIR / f"two_up-{stamp}-{safe}.db"
    try:
        _copy(src, dst)
    except sqlite3.Error as exc:
        dst.unlink(missing_ok=True)
        raise BackupError(f"backup failed: {exc}") from exc
    if not _integrity_ok(dst):
        dst.unlink(missing_ok=True)
        raise BackupError("backup failed integrity_check")

    counts = row_counts(dst)
    summary = " ".join(f"{k}={v}" for k, v in counts.items())
    if _looks_empty(counts):
        print(f"[backup] WARNING {dst.name} looks empty ({summary}); not pruning")
    else:
        removed = prune()
        print(f"[backup] {dst.name} ({summary}); pruned {len(removed)}")
    return dst


def restore_db(backup_path) -> Path:
    """Replace the live DB with a backup. Takes a pre-restore backup first."""
    src = Path(backup_path)
    if not src.is_file():
        candidate = BACKUP_DIR / backup_path
        if candidate.is_file():
            src = candidate
        else:
            raise BackupError(f"backup not found: {backup_path}")
    if not _integrity_ok(src):
        raise BackupError(f"{src.name} failed integrity_check; not restoring")

    live = Path(DB_NAME)
    if live.is_file():
        pre = backup_db("pre-restore")
        print(f"[restore] current DB saved as {pre.name}")
    _copy(src, live)
    counts = row_counts(live)
    print(f"[restore] restored {src.name} -> {live}")
    print("[restore] " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return live


def main(argv=None):
    parser = argparse.ArgumentParser(description="two_up.db backup / restore")
    parser.add_argument("--label", default="manual")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--restore", metavar="FILE")
    args = parser.parse_args(argv)

    try:
        if args.list:
            files = list_backups()
            if not files:
                print(f"[backup] no backups in {BACKUP_DIR}")
            for f in files:
                counts = row_counts(f)
                size_mb = f.stat().st_size / 1e6
                print(f"{f.name}  {size_mb:.1f}MB  "
                      + " ".join(f"{k}={v}" for k, v in counts.items()))
            return 0
        if args.restore:
            restore_db(args.restore)
            return 0
        backup_db(args.label)
        return 0
    except BackupError as exc:
        print(f"[backup] ERROR {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
