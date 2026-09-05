# Front-end API + RevenueCat

## Server

```bash
cd ~/TurnaroundIQ
pip install fastapi uvicorn
export REVENUECAT_SECRET_API_KEY=sk_xxxxxxxx
export REVENUECAT_WEBHOOK_AUTH=your_webhook_token
export REVENUECAT_ENTITLEMENT=pro
uvicorn api.app:app --host 0.0.0.0 --port 8080
```

## RevenueCat dashboard

1. Create entitlement `pro`.
2. Attach your App Store / Play product to `pro`.
3. Project settings → API keys → copy **Secret** key into `REVENUECAT_SECRET_API_KEY`.
4. Integrations → Webhooks → URL `https://YOUR_DOMAIN/webhooks/revenuecat`.
5. Set the webhook Authorization header to the same value as `REVENUECAT_WEBHOOK_AUTH`.

## App

Purchases SDK identifies the user with `app_user_id`. Every API call:

```
Authorization: Bearer <app_user_id>
GET /me
GET /opportunities
```

`402` = not subscribed. `401` = missing id.
