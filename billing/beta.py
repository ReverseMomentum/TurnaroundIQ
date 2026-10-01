"""
Free beta: every signed-in web account gets Pro until a date, then it switches off.

Env (all optional; unset BETA_FREE_UNTIL = no beta):
  BETA_FREE_UNTIL      last day of the beta, YYYY-MM-DD (inclusive, UK time)
  BETA_MAX_USERS       only the first N accounts to sign up get beta access (0/unset = no cap)
  BETA_FOUNDER_PRICE   price shown to beta users for subscribing early, e.g. "£6.99"

Paying subscribers and grant_pro.sh comps are unaffected: beta access is only
added on top of them, never written to the subscribers table.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from database import get_db

UK = ZoneInfo("Europe/London")


def beta_until():
    raw = os.environ.get("BETA_FREE_UNTIL", "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def beta_ends_at(last_day=None):
    """The moment the beta ends: midnight UK time after its last day, as UTC."""
    last_day = last_day or beta_until()
    if not last_day:
        return None
    return datetime.combine(last_day + timedelta(days=1), time(0), tzinfo=UK).astimezone(timezone.utc)


def beta_open(now=None):
    end = beta_ends_at()
    return bool(end and (now or datetime.now(timezone.utc)) < end)


def max_users():
    try:
        return max(0, int(os.environ.get("BETA_MAX_USERS", "0") or 0))
    except ValueError:
        return 0


def _signup_rank(user_id):
    """1 for the first account ever created, 2 for the next, … None if unknown."""
    conn = get_db()
    try:
        row = conn.execute("SELECT created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        n = conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at < ? OR (created_at = ? AND id <= ?)",
            (row[0], row[0], user_id),
        ).fetchone()[0]
        return int(n)
    except Exception:
        return None
    finally:
        conn.close()


def covers(user_id, now=None):
    """True if this account gets Pro through the beta right now."""
    if not user_id or not user_id.startswith("u_") or not beta_open(now):
        return False
    cap = max_users()
    if not cap:
        return True
    rank = _signup_rank(user_id)
    return rank is not None and rank <= cap


def info(user_id, now=None):
    """What /me reports about the beta for this account."""
    last_day = beta_until()
    return {
        "open": beta_open(now),
        "active": covers(user_id, now),
        "until": last_day.isoformat() if last_day else None,
        "ends_at": beta_ends_at(last_day).isoformat() if last_day else None,
        "founder_price": os.environ.get("BETA_FOUNDER_PRICE", "").strip() or None,
    }
