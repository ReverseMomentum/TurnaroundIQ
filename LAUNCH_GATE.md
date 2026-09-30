# Launch gate

No public store push until every **Must-have** is ticked with evidence.
Owner key: **F** founder/eng (runs it) · **PM** (tracks, verifies evidence).
How-to for each step: `deploy/RUNBOOK.md`.

## Must-have

Status as of 2026-09-30. ✅ done · 🟡 built, needs evidence · ⬜ not started.

| # | Gate | Status | Remaining to tick | Owner |
|---|---|---|---|---|
| 1 | API stable, Pro-only opportunities | ✅ systemd + Caddy, HTTPS live at `api.turnaroundiq.co.uk`; 401/402 enforced + tested; `/health` 503 on empty DB | 7 days of `/health` 200 | F |
| 2 | RevenueCat end-to-end (web: Stripe via Web Purchase Link) | 🟢 **LIVE 2026-09-30**: real £9.99 purchase via production purchase link → Stripe subscription active → `/me` shows Pro (entitlement `pro`, V1 secret key); non-subscriber → 402 ; webhook live in RC dashboard, signed 200 / wrong secret 401 | Cancel/refund → expiry → 402 observed on a real account | F → PM |
| 3 | Match-day collection unattended | 🟡 cron installed; season-to-date filled; events batched, retries, quota reserve | 2 match weekends without manual runs (`logs/live.log`) | F |
| 4 | Automated `two_up.db` backup | ✅ nightly + post-live + before train/historical; **restore drill PASS 2026-09-30 12:20 UTC** (match_results 2381, historical 44603) | Off-box copy (should-have) | F |
| 5 | Fresh opportunities, no stale junk | ✅ finished matches never served; kicked-off games dropped | Spot-check on 3 match days | PM |
| 6 | Paper log running | 🟡 cron opens + settles FTA / Early / Chaos daily | 2+ weekends settled, reviewed weekly | PM |
| 7 | App loads Pro / Opportunities / Early / Chaos | 🟡 **LIVE 2026-09-30**: web app at `app.turnaroundiq.co.uk`, emailed-code sign-in verified on iPhone (Brevo SMTP). Built: email-code sign-in, Stripe checkout via RevenueCat Web Purchase Link, all screens on live API; sign-in → paywall → Pro → reload → sign-out verified in headless browser against a local API | DNS record, SMTP + AUTH_SECRET, RC Web Billing + purchase link, `bash deploy/build_web.sh`, test on iPhone | F |
| 8 | Disclaimer copy | 🟡 on every data screen + paywall (estimates not tips, 18+, BeGambleAware) | Founder/PM approve wording; Terms + Privacy URLs | PM |

### Model (for honest copy)

FTA% = chance the team goes 2 up **and** fails to win (full event, ~2% average).
Walk-forward on 3½ unseen seasons: top-10% picks happened ~1.5× the average
(3.2% vs 2.1%); stage AUCs ~0.67. Free historical odds tested: no gain for
FTA% ranking, so no paid odds feed for the model. Claims allowed: "top-ranked
picks turned around ~1.5× as often as average in out-of-sample testing".
Not allowed: profit, "high confidence", "predicts turnarounds".

### RevenueCat steps (founder)

1. Dashboard → Integrations → Webhooks → URL `https://api.turnaroundiq.co.uk/webhooks/revenuecat`,
   Authorization header = value from `sudo grep REVENUECAT_WEBHOOK_AUTH /etc/turnaroundiq.env`.
2. VPS: `bash scripts/rc_check.sh webhook` → 200 / 401.
3. TestFlight sandbox user: `bash scripts/rc_check.sh user <appUserID>` → 402 before purchase,
   200 after, 402 again after sandbox expiry (minutes).

### Soft-launch access

Testers sign in once at app.turnaroundiq.co.uk, then:
`bash scripts/grant_pro.sh their@email.com 60` (free Pro, 60 days) ·
`bash scripts/grant_pro.sh --list` · `... revoke`.

### App (mobile/)

Build steps and the RevenueCat checklist: `mobile/README.md`. Live monitoring
shows "coming soon" (no in-play backend in v1 scope).

## Should-have

- [ ] Walk-forward / calibration notes in plain language
- [ ] League baseline context on opportunities (FTA% vs league)
- [x] Runbook: restart API, live, train, restore — `deploy/RUNBOOK.md`
- [x] Domain + HTTPS — `api.turnaroundiq.co.uk`

## Soft-launch criteria (proposal — founder + PM to agree)

Closed group (10–25 users, TestFlight / internal track) starts when:

1. All Must-have rows 1–6 ticked with evidence
2. 14 consecutive days with: every scheduled live run succeeding or recovered same day, zero `critical` health events, a backup every day
3. Paper log: ≥ 2 match weekends settled across FTA / Early / Chaos, reviewed against predicted bands — reported as-is, good or bad
4. Restore drill done and dated

Public release after 2+ weeks of soft launch with no P0 incident and no crash reports on the three core screens.

**Rollback:** redeploy previous git tag (`git checkout <tag> && systemctl restart turnaroundiq-api`), restore last good backup if data is affected, pause paywall in RevenueCat if the product is unusable.

## Scope freeze (v1)

In: FTA Opportunities, Early Goal Hunter, Chaos Factor, paper tracking, Pro subscription.
Out until after launch: Mismatch Meter (API off by default, `FEATURE_MISMATCH=1`), per-league models, paid odds APIs, arb/golf/HMM tools.
