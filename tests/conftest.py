"""
Pytest setup: every test run gets a throwaway DB + backup dir, so the suite
can never touch the real two_up.db.
"""

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="tiq-test-"))
os.environ["TURNAROUNDIQ_DB"] = str(_TMP / "two_up.db")
os.environ["BACKUP_DIR"] = str(_TMP / "backups")
os.environ["TURNAROUNDIQ_ENV_FILE"] = str(_TMP / "none.env")
os.environ["API_FOOTBALL_KEY"] = ""
os.environ["REVENUECAT_SECRET_API_KEY"] = ""
os.environ["REVENUECAT_WEBHOOK_AUTH"] = "test-webhook-secret"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Legacy scripts in tests/ hit live APIs at import time — not unit tests.
collect_ignore = ["test_xg.py", "backtest.py", "feature_config.py"]
