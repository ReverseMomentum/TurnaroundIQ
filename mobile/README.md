# TurnaroundIQ app (iOS / Android via Capacitor)

Your React UI, wired to `https://api.turnaroundiq.co.uk`, with App Store /
Google Play subscriptions through RevenueCat.

## One-time setup (on your Mac — iOS needs Xcode; Android needs Android Studio)

```bash
cd TurnaroundIQ/mobile
npm install
cp .env.example .env        # then fill in the RevenueCat appl_/goog_ keys
npx cap add ios
npx cap add android
```

## Run

```bash
npm run ios        # builds, syncs, opens Xcode -> press Run
npm run android    # builds, syncs, opens Android Studio -> press Run
npm run dev        # browser preview (no purchases; set VITE_DEV_USER_ID)
```

## RevenueCat checklist

1. Products in App Store Connect / Play Console, attached to entitlement `pro`.
2. An Offering marked *current* containing those packages (the paywall lists it).
3. Public SDK keys in `.env`: `VITE_RC_IOS_KEY=appl_…`, `VITE_RC_ANDROID_KEY=goog_…`.
4. Webhook -> `https://api.turnaroundiq.co.uk/webhooks/revenuecat`.
5. Apple requires Terms (EULA) + Privacy links on the paywall: set
   `VITE_TERMS_URL` and `VITE_PRIVACY_URL`.

## What's real vs coming soon

| Screen | Data |
|---|---|
| Dashboard, Opportunities, Early Goal Hunter, Chaos Factor | Live API (Pro) |
| Opportunity detail -> Track (paper) | `POST /tracked` |
| My Bets | `GET /tracked`, "Settle finished" -> `/paper/auto-settle` |
| Settings | `/me`, prefs saved via `PATCH /me/prefs`, restore / manage subscription |
| Calculator | Local maths (same formulas as the server) |
| Live monitoring | Coming soon (no in-play backend yet) |
| Model testing | Only with `VITE_SHOW_DEV_TOOLS=true` and your id in `ADMIN_USER_IDS` |

The "Support ID" in Settings is the RevenueCat appUserID — use it with
`scripts/rc_check.sh user '<id>'` on the VPS.
