"""
RevenueCat v1 subscriber lookup + local cache.

Env:
  REVENUECAT_SECRET_API_KEY   sk_...
  REVENUECAT_WEBHOOK_AUTH     Authorization value RC sends
  REVENUECAT_ENTITLEMENT      default: pro
"""

from datetime import datetime, timezone
import os
from urllib.parse import quote

import requests

from database import get_db

RC_API = "https://api.revenuecat.com/v1"
ENTITLEMENT = os.environ.get("REVENUECAT_ENTITLEMENT", "pro")


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
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def upsert_subscriber(app_user_id, entitled, entitlement=None, expires_at=None,
                      product_id=None, environment=None, last_event=None):
    ensure_tables()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO subscribers (
            app_user_id, entitled, entitlement, expires_at,
            product_id, environment, last_event, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(app_user_id) DO UPDATE SET
            entitled = excluded.entitled,
            entitlement = excluded.entitlement,
            expires_at = excluded.expires_at,
            product_id = excluded.product_id,
            environment = excluded.environment,
            last_event = excluded.last_event,
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
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def cached_entitled(app_user_id):
    ensure_tables()
    conn = get_db()
    row = conn.execute(
        "SELECT entitled, expires_at FROM subscribers WHERE app_user_id = ?",
        (app_user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    entitled, expires_at = row
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                return False
        except ValueError:
            pass
    return bool(entitled)


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
    if expires:
        try:
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                return False, expires, item.get("product_identifier")
        except ValueError:
            pass
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
    entitled, expires, product = entitlement_from_subscriber(payload)
    upsert_subscriber(
        app_user_id,
        entitled,
        entitlement=ENTITLEMENT,
        expires_at=expires,
        product_id=product,
        last_event="GET /subscribers",
    )
    return entitled


def apply_webhook(body):
    event = (body or {}).get("event") or {}
    user_id = event.get("app_user_id") or event.get("original_app_user_id")
    if not user_id:
        return False
    kind = event.get("type") or ""
    ids = event.get("entitlement_ids") or []
    if event.get("entitlement_id"):
        ids = list(set(list(ids) + [event.get("entitlement_id")]))
    expires_ms = event.get("expiration_at_ms")
    expires_at = None
    if expires_ms:
        expires_at = datetime.fromtimestamp(expires_ms / 1000, tz=timezone.utc).isoformat()
    lost = kind in {"EXPIRATION", "CANCELLATION", "BILLING_ISSUE"}
    entitled = (ENTITLEMENT in ids or not ids) and not lost
    if kind == "CANCELLATION" and expires_at:
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            entitled = exp > datetime.now(timezone.utc)
        except ValueError:
            entitled = False
    upsert_subscriber(
        user_id,
        entitled,
        entitlement=ENTITLEMENT,
        expires_at=expires_at,
        product_id=event.get("product_id"),
        environment=event.get("environment"),
        last_event=kind,
    )
    try:
        is_entitled(user_id, refresh=True)
    except Exception:
        pass
    return True
