"""
"Refresh odds" button: re-price the next 24h of games on demand, safely shared.

Anyone with Pro can press it, so it is guarded:
  - one refresh at a time, and never alongside the cron odds job (same lock file)
  - a shared cooldown (ODDS_REFRESH_COOLDOWN_S, default 15 min): a press during
    it just reports when prices were last updated
  - a daily api-sports call budget for button refreshes (ODDS_REFRESH_DAILY_CALLS,
    default 1500) on top of the api-sports client's own reserve
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from collectors import odds_apisports

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "logs" / "odds.lock"  # shared with scripts/cron_job.sh odds
COOLDOWN_S = int(os.environ.get("ODDS_REFRESH_COOLDOWN_S", "900"))
DAILY_CALLS = int(os.environ.get("ODDS_REFRESH_DAILY_CALLS", "1500"))
WINDOW_HOURS = 24

_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,   # epoch seconds of the last completed refresh
    "last": None,          # summary of the last refresh
    "error": None,
    "day": None,
    "calls_today": 0,
}
_guard = threading.Lock()


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def status():
    now = time.time()
    wait = 0
    if _state["finished_at"]:
        wait = max(0, int(COOLDOWN_S - (now - _state["finished_at"])))
    return {
        "running": _state["running"],
        "last_refresh_at": _iso(_state["finished_at"]),
        "retry_after_s": wait,
        "last": _state["last"],
        "error": _state["error"],
    }


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _run(budget):
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOCK_FILE, "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                _state["error"] = "scheduled odds update in progress — try again shortly"
                return
            summary = odds_apisports.refresh(WINDOW_HOURS, max_calls=budget, log=lambda *_: None)
            try:  # real exchange prices too, if Betfair is set up (never blocks the bookie odds)
                from collectors import betfair, betfair_football
                if betfair.configured():
                    bf = betfair_football.refresh(WINDOW_HOURS, log=lambda *_: None)
                    summary = {**summary, "betfair_matched": bf["matched"]}
            except Exception as exc:
                summary = {**summary, "betfair_error": str(exc)[:200]}
            _state["last"] = summary
            _state["calls_today"] += summary.get("calls", 0)
            _state["finished_at"] = time.time()
    except Exception as exc:  # never take the API down over odds
        _state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _state["running"] = False


def start():
    """Kick off a background refresh if allowed. Returns (started: bool, status dict)."""
    with _guard:
        if _state["running"]:
            return False, {**status(), "reason": "running"}
        st = status()
        if st["retry_after_s"] > 0:
            return False, {**st, "reason": "cooldown"}
        if _state["day"] != _today():
            _state["day"], _state["calls_today"] = _today(), 0
        budget = min(200, DAILY_CALLS - _state["calls_today"])
        if budget <= 2:
            return False, {**st, "reason": "daily_limit"}
        _state.update(running=True, started_at=time.time(), error=None)
    threading.Thread(target=_run, args=(budget,), daemon=True).start()
    return True, {**status(), "reason": "started"}
