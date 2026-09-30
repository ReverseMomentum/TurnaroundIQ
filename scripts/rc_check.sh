#!/usr/bin/env bash
# RevenueCat end-to-end checks against the live HTTPS API.
#   bash scripts/rc_check.sh user <appUserID>   # /me entitlement + /opportunities status
#   bash scripts/rc_check.sh webhook            # send a signed TEST webhook
#   bash scripts/rc_check.sh diag <u_id>        # what RevenueCat itself says about an account
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
  diag)
    # Ask RevenueCat directly what it knows about an account (needs the V1 secret key).
    ID="${2:?usage: rc_check.sh diag <u_accountID>}"
    ENV=/etc/turnaroundiq.env
    KEY="$(sudo grep -E '^REVENUECAT_SECRET_API_KEY=' $ENV | cut -d= -f2-)"
    WANT="$(sudo grep -E '^REVENUECAT_ENTITLEMENT=' $ENV | cut -d= -f2-)"
    echo "server expects entitlement: ${WANT:-pro}"
    [ -z "$KEY" ] && { echo "REVENUECAT_SECRET_API_KEY not set in $ENV"; exit 1; }
    echo "secret key starts: ${KEY:0:6}…  (V1 keys start sk_)"
    curl -s -H "Authorization: Bearer $KEY" "https://api.revenuecat.com/v1/subscribers/$ID" \
      | WANT="${WANT:-pro}" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
s = d.get("subscriber")
if s is None:
    print("RevenueCat said:", d.get("message") or d); sys.exit()
ents = s.get("entitlements") or {}
print("RevenueCat entitlements:", {k: v.get("expires_date") for k, v in ents.items()} or "NONE")
print("RevenueCat subscriptions:", list((s.get("subscriptions") or {}).keys()) or "NONE")
want = os.environ["WANT"]
if want in ents:
    print("OK: entitlement matches - /me should show Pro")
elif ents:
    print("MISMATCH: RevenueCat grants", list(ents), "but server expects", want)
elif s.get("subscriptions"):
    print("Purchase found but NO entitlement: attach the product to the entitlement in RevenueCat")
else:
    print("RevenueCat has no purchase for this ID")
'
    code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health"); echo "API health HTTP $code"
    ;;
  *) echo "usage: rc_check.sh user <appUserID> | webhook | diag <u_accountID>"; exit 1;;
esac
