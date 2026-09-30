#!/usr/bin/env bash
# RevenueCat end-to-end checks against the live HTTPS API.
#   bash scripts/rc_check.sh user <appUserID>   # /me entitlement + /opportunities status
#   bash scripts/rc_check.sh webhook            # send a signed TEST webhook
BASE="${API_BASE:-https://api.turnaroundiq.co.uk}"
case "${1:-}" in
  user)
    ID="${2:?usage: rc_check.sh user <appUserID>}"
    echo "--- /me"
    curl -s -H "Authorization: Bearer $ID" "$BASE/me" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print({k: d.get(k) for k in ("entitled","status","expires_at","product_id","environment")})'
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $ID" "$BASE/opportunities?limit=1")
    echo "--- /opportunities -> HTTP $code  (200 = Pro, 402 = paywall)"
    ;;
  webhook)
    AUTH="$(sudo grep -E '^REVENUECAT_WEBHOOK_AUTH=' /etc/turnaroundiq.env | cut -d= -f2-)"
    [ -z "$AUTH" ] && { echo "REVENUECAT_WEBHOOK_AUTH not set in /etc/turnaroundiq.env"; exit 1; }
    code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/webhooks/revenuecat" \
      -H "Authorization: $AUTH" -H "Content-Type: application/json" \
      -d '{"event":{"type":"TEST","app_user_id":"rc_webhook_test"}}')
    bad=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/webhooks/revenuecat" \
      -H "Authorization: wrong" -H "Content-Type: application/json" -d '{}')
    echo "signed webhook -> HTTP $code (want 200); wrong secret -> HTTP $bad (want 401)"
    ;;
  *) echo "usage: rc_check.sh user <appUserID> | webhook"; exit 1;;
esac
