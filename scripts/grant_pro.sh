#!/usr/bin/env bash
# Give (or remove) Pro for a signed-in web account — soft-launch testers, comps.
#   bash scripts/grant_pro.sh someone@example.com          # Pro for 60 days
#   bash scripts/grant_pro.sh someone@example.com 30       # Pro for 30 days
#   bash scripts/grant_pro.sh someone@example.com revoke   # back to Free
#   bash scripts/grant_pro.sh --list                       # all accounts + status
# The person must have signed in once first (so their account exists).
cd "$(dirname "$0")/.."
exec venv/bin/python - "$@" <<'PY'
import sys
from datetime import datetime, timedelta, timezone
from database import get_db
from billing.revenuecat import upsert_subscriber, ensure_tables
from api.auth import ensure_auth_tables

ensure_tables(); ensure_auth_tables()
args = sys.argv[1:]
conn = get_db()
if not args or args[0] == "--list":
    rows = conn.execute("""SELECT u.email, u.id, COALESCE(s.status,'free'), s.expires_at
        FROM users u LEFT JOIN subscribers s ON s.app_user_id = u.id ORDER BY u.created_at""").fetchall()
    for email, uid, status, exp in rows:
        print(f"{email:<35} {status:<10} {(exp or '')[:10]}")
    print(f"{len(rows)} accounts")
    sys.exit(0)
email = args[0].strip().lower()
row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
if not row:
    sys.exit(f"No account for {email} — they need to sign in at app.turnaroundiq.co.uk first")
uid = row[0]
if len(args) > 1 and args[1] == "revoke":
    upsert_subscriber(uid, False, entitlement="pro", status="expired", last_event="MANUAL_REVOKE")
    print(f"Pro removed for {email}")
else:
    days = int(args[1]) if len(args) > 1 else 60
    exp = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    upsert_subscriber(uid, True, entitlement="pro", expires_at=exp, status="active",
                      product_id="comp", environment="MANUAL", last_event="MANUAL_GRANT")
    print(f"Pro granted to {email} until {exp[:10]}")
PY
