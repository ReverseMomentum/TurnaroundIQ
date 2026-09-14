"""
RevenueCat v1 subscriber lookup + local cache + user prefs.

Env:
  REVENUECAT_SECRET_API_KEY   sk_...
  REVENUECAT_WEBHOOK_AUTH     Authorization value RC sends
  REVENUECAT_ENTITLEMENT      default: pro
"""

from datetime import datetime, timezone
import json
import os
from urllib.parse import quote

import requests

from database import get_db

RC_API = "https://api.revenuecat.com/v1"
ENTITLEMENT = os.environ.get("REVENUECAT_ENTITLEMENT", "pro")

EXPIRED_EVENTS = {"EXPIRATION", "REFUND", "REVOKE"}
SOFT_EVENTS = {"CANCELLATION", "BILLING_ISSUE"}
ACTIVE_EVENTS = {
    "INITIAL_PURCHASE",
    "RENEWAL",
    "UNCANCELLATION",
    "PRODUCT_CHANGE",
    "NON_RENEWING_PURCHASE",
}

DEFAULT_PREFS = {
    "default_stake": 100,
    "default_commission": 2.0,
    "risk_warning_pct": 5.0,
    "notify_opportunity": True,
    "notify_fixture_starting": True,
    "notify_live_trigger": True,
    "notify_exchange_entry": True,
}


def _secret():
    return os.environ.get("REVENUECAT_SECRET_API_KEY", "").strip()


def webhook_auth_ok(header_value):
    expected = os.environ.get("REVENUECAT_WEBHOOK_AUTH", "").strip()
    if not expected:
        return False
    if not header_value:
        return False
    got = header_value.replace("Bearer ", "").strip()
    return got == expected or header_value.strip() == expected


def ensure_tables():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            app_user_id TEXT PRIMARY KEY,
            entitled INTEGER DEFAULT 0,
            entitlement TEXT,
            expires_at TEXT,
            product_id TEXT,
            environment TEXT,
            last_event TEXT,
            status TEXT,
            updated_at TEXT
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(subscribers)")}
    if "status" not in cols:
        conn.execute("ALTER TABLE subscribers ADD COLUMN status TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_prefs (
            app_user_id TEXT PRIMARY KEY,
            prefs_json TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def upsert_subscriber(
    app_user_id,
    entitled,
    entitlement=None,
    expires_at=None,
    product_id=None,
    environment=None,
    last_event=None,
    status=None,
):
    ensure_tables()
    if status is None:
        status = "active" if entitled else "expired"
    conn = get_db()
    conn.execute(
        """
        INSERT INTO subscribers (
            app_user_id, entitled, entitlement, expires_at,
            product_id, environment, last_event, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(app_user_id) DO UPDATE SET
            entitled = excluded.entitled,
            entitlement = excluded.entitlement,
            expires_at = excluded.expires_at,
            product_id = excluded.product_id,
            environment = excluded.environment,
            last_event = excluded.last_event,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (
            app_user_id,
            1 if entitled else 0,
            entitlement,
            expires_at,
            product_id,
            environment,
            last_event,
            status,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_subscriber_row(app_user_id):
    ensure_tables()
    conn = get_db()
    row = conn.execute(
        """
        SELECT app_user_id, entitled, entitlement, expires_at,
               product_id, environment, last_event, status, updated_at
        FROM subscribers WHERE app_user_id = ?
        """,
        (app_user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    keys = [
        "app_user_id", "entitled", "entitlement", "expires_at",
        "product_id", "environment", "last_event", "status", "updated_at",
    ]
    return dict(zip(keys, row))


def get_prefs(app_user_id):
    ensure_tables()
    conn = get_db()
    row = conn.execute(
        "SELECT prefs_json FROM user_prefs WHERE app_user_id = ?",
        (app_user_id,),
    ).fetchone()
    conn.close()
    prefs = dict(DEFAULT_PREFS)
    if row and row[0]:
        try:
            prefs.update(json.loads(row[0]))
        except json.JSONDecodeError:
            pass
    return prefs


def save_prefs(app_user_id, patch):
    ensure_tables()
    current = get_prefs(app_user_id)
    for key, value in (patch or {}).items():
        if key in DEFAULT_PREFS:
            current[key] = value
    conn = get_db()
    conn.execute(
        """
        INSERT INTO user_prefs (app_user_id, prefs_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(app_user_id) DO UPDATE SET
            prefs_json = excluded.prefs_json,
            updated_at = excluded.updated_at
        """,
        (app_user_id, json.dumps(current), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return current


def _not_expired(expires_at):
    if not expires_at:
        return True
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return exp > datetime.now(timezone.utc)
    except ValueError:
        return True


def cached_entitled(app_user_id):
    row = get_subscriber_row(app_user_id)
    if not row:
        return None
    if not row["entitled"]:
        return False
    if not _not_expired(row.get("expires_at")):
        return False
    return True


def fetch_subscriber(app_user_id):
    key = _secret()
    if not key:
        return None
    url = f"{RC_API}/subscribers/{quote(app_user_id, safe='')}"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        timeout=20,
    )
    if response.status_code == 404:
        return {"subscriber": {"entitlements": {}}}
    response.raise_for_status()
    return response.json()


def entitlement_from_subscriber(payload, name=ENTITLEMENT):
    entitlements = (payload or {}).get("subscriber", {}).get("entitlements") or {}
    item = entitlements.get(name)
    if not item:
        return False, None, None
    expires = item.get("expires_date")
    if expires and not _not_expired(expires):
        return False, expires, item.get("product_identifier")
    return True, expires, item.get("product_identifier")


def is_entitled(app_user_id, refresh=False):
    if not app_user_id:
        return False
    if not refresh:
        cached = cached_entitled(app_user_id)
        if cached is not None:
            return cached
    try:
        payload = fetch_subscriber(app_user_id)
    except Exception:
        cached = cached_entitled(app_user_id)
        return bool(cached)
    if payload is None:
        cached = cached_entitled(app_user_id)
        return bool(cached)
    entitled, expires, product = entitlement_from_subscriber(payload)
    upsert_subscriber(
        app_user_id,
        entitled,
        entitlement=ENTITLEMENT,
        expires_at=expires,
        product_id=product,
        last_event="GET /subscribers",
        status="active" if entitled else "expired",
    )
    return entitled


def apply_webhook(body):
    event = (body or {}).get("event") or {}
    user_id = event.get("app_user_id") or event.get("original_app_user_id")
    if not user_id:
        return False
    kind = (event.get("type") or "").upper()
    ids = list(event.get("entitlement_ids") or [])
    if event.get("entitlement_id"):
        ids = list(set(ids + [event.get("entitlement_id")]))
    expires_ms = event.get("expiration_at_ms")
    expires_at = None
    if expires_ms:
        expires_at = datetime.fromtimestamp(
            expires_ms / 1000, tz=timezone.utc
        ).isoformat()

    product_id = event.get("product_id")
    environment = event.get("environment")

    if kind in EXPIRED_EVENTS:
        entitled = False
        status = "expired" if kind == "EXPIRATION" else kind.lower()
    elif kind in SOFT_EVENTS:
        entitled = _not_expired(expires_at) if expires_at else True
        status = "cancelled" if kind == "CANCELLATION" else "billing_issue"
    elif kind in ACTIVE_EVENTS:
        entitled = (ENTITLEMENT in ids) if ids else True
        status = "active"
    else:
        try:
            return bool(is_entitled(user_id, refresh=True))
        except Exception:
            entitled = cached_entitled(user_id) or False
            status = "unknown"

    upsert_subscriber(
        user_id,
        entitled,
        entitlement=ENTITLEMENT,
        expires_at=expires_at,
        product_id=product_id,
        environment=environment,
        last_event=kind,
        status=status,
    )
    try:
        is_entitled(user_id, refresh=True)
    except Exception:
        pass
    return True
