# TurnaroundIQ API (FastAPI)

Mobile apps talk to this service. Python collectors stay on the same VPS and fill `two_up.db`; this API only reads DB + enforces RevenueCat.

## Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| GET | `/health` | none | DB ping |
| GET | `/me` | Bearer app_user_id | entitlement, expires_at, prefs |
| GET | `/me/prefs` | Bearer | settings defaults |
| PATCH | `/me/prefs` | Bearer | stake, commission, notification toggles |
| GET | `/opportunities` | Bearer + **Pro** | 402 if expired / free |
| POST | `/webhooks/revenuecat` | RC webhook auth | purchase / expiry |

## Local / VPS test (before public launch)

```bash
cd ~/TurnaroundIQ
source venv/bin/activate
pip install fastapi uvicorn pydantic

export REVENUECAT_SECRET_API_KEY=sk_test_or_live
export REVENUECAT_WEBHOOK_AUTH=pick_a_long_random_string
export REVENUECAT_ENTITLEMENT=pro
export CORS_ORIGINS=*

uvicorn api.app:app --host 127.0.0.1 --port 8080
```

```bash
curl -s http://127.0.0.1:8080/health
curl -s -H "Authorization: Bearer test_user_1" http://127.0.0.1:8080/me
curl -s -H "Authorization: Bearer test_user_1" http://127.0.0.1:8080/opportunities
# expect 402 until RC marks test_user_1 as pro
```

Simulate expiry (after a real webhook or manual DB row):

```bash
sqlite3 two_up.db "SELECT * FROM subscribers;"
```

## RevenueCat dashboard

1. Entitlement id: `pro` (must match `REVENUECAT_ENTITLEMENT`).
2. Attach App Store + Play products to `pro`.
3. Project → API keys → **Secret** → `REVENUECAT_SECRET_API_KEY`.
4. Integrations → Webhooks → `https://YOUR_DOMAIN/webhooks/revenuecat`.
5. Webhook Authorization header = `REVENUECAT_WEBHOOK_AUTH`.
6. Sandbox purchases for TestFlight; production keys only at launch.

## App contract

```
Authorization: Bearer <Purchases.appUserID>
```

- `401` — missing id  
- `402` — not entitled (free or expired) → show paywall / Manage subscription  
- `/me.entitled` drives the **Pro** badge on Settings  

## Production (when you are ready)

1. Put env vars in `/etc/turnaroundiq.env` (not in git).
2. Install systemd unit from `deploy/turnaroundiq-api.service`.
3. Terminate TLS with Caddy/nginx → `127.0.0.1:8080`.
4. Restrict `CORS_ORIGINS` if a web client is used.
5. Keep running collectors + `run.py train` on cron; API does not retrain.

## Next.js

If the app BFF is Next.js, either:

- Proxy these routes to this FastAPI service, or  
- Call this host directly from the mobile apps (simplest).

Do not re-implement RevenueCat webhooks in two places.
