"""
Data health — shared by GET /health and `python -u run.py health`.

"critical" means the product cannot serve real intel (no DB / no results). "warnings" mean it is degraded (stale results, old backup, missing
keys). CLI exits 2 on critical, 1 on warnings, 0 when healthy.

Env:
  HEALTH_MAX_RESULTS_AGE_HOURS   default 72
  HEALTH_MAX_BACKUP_AGE_HOURS    default 36
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from constants import API_FOOTBALL_KEY
from database import DB_NAME
from ops.backup import CORE_TABLES, list_backups

# FTA path model (V6). Without it the app falls back to profile rates.
MODEL_FILE = ROOT / "fta_path_model.pkl"
MAX_RESULTS_AGE_H = float(os.environ.get("HEALTH_MAX_RESULTS_AGE_HOURS", "72"))
MAX_BACKUP_AGE_H = float(os.environ.get("HEALTH_MAX_BACKUP_AGE_HOURS", "36"))


def _age_hours(iso_value):
    if not iso_value:
        return None
    try:
        ts = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - ts).total_seconds() / 3600, 1)


def check() -> dict:
    critical, warnings = [], []
    counts = {t: None for t in CORE_TABLES}
    last_result_at = None

    db = Path(DB_NAME)
    if not db.is_file():
        critical.append(f"db_missing:{db}")
    else:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                tables = {
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                for t in CORE_TABLES:
                    if t in tables:
                        counts[t] = conn.execute(
                            f"SELECT COUNT(*) FROM {t}"
                        ).fetchone()[0]
                if "match_results" in tables:
                    last_result_at = conn.execute(
                        "SELECT MAX(processed_at) FROM match_results"
                    ).fetchone()[0]
            finally:
                conn.close()
        except sqlite3.Error as exc:
            critical.append(f"db_error:{exc}")

    if not critical:
        if not counts["match_results"]:
            critical.append("match_results_empty")
        if not counts["team_stats"]:
            critical.append("team_stats_empty")
        if not counts["training_data"]:
            warnings.append("training_data_empty")

    if not MODEL_FILE.is_file():
        warnings.append("path_model_missing_run_train")

    results_age = _age_hours(last_result_at)
    if results_age is not None and results_age > MAX_RESULTS_AGE_H:
        warnings.append(f"results_stale:{results_age}h")

    backups = list_backups()
    backup_age = None
    if not backups:
        warnings.append("no_backups")
    else:
        mtime = datetime.fromtimestamp(backups[-1].stat().st_mtime, tz=timezone.utc)
        backup_age = round(
            (datetime.now(timezone.utc) - mtime).total_seconds() / 3600, 1
        )
        if backup_age > MAX_BACKUP_AGE_H:
            warnings.append(f"backup_stale:{backup_age}h")

    if not API_FOOTBALL_KEY:
        warnings.append("api_football_key_missing")
    if not os.environ.get("REVENUECAT_SECRET_API_KEY"):
        warnings.append("revenuecat_secret_missing")
    if not os.environ.get("REVENUECAT_WEBHOOK_AUTH"):
        warnings.append("revenuecat_webhook_auth_missing")

    status = "critical" if critical else ("degraded" if warnings else "ok")
    return {
        "status": status,
        "critical": critical,
        "warnings": warnings,
        "row_counts": counts,
        "last_result_processed_at": last_result_at,
        "results_age_hours": results_age,
        "latest_backup": backups[-1].name if backups else None,
        "backup_age_hours": backup_age,
        "model_present": MODEL_FILE.is_file(),
    }


def main() -> int:
    report = check()
    print(json.dumps(report, indent=2))
    if report["critical"]:
        return 2
    if report["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
