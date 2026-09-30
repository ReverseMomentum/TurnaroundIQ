# Launch gate

No public store push until every **Must-have** is ticked with evidence.
Owner key: **F** founder/eng (runs it) · **PM** (tracks, verifies evidence).
How-to for each step: `deploy/RUNBOOK.md`.

## Must-have

| # | Gate | Code status | Remaining to tick | Owner |
|---|---|---|---|---|
| 1 | API stable, Pro-only opportunities | ✅ 401/402 enforced + tested; real `/health` (503 on empty DB) | Move API to systemd + Caddy; 7 days of `/health` 200 | F |
| 2 | RevenueCat end-to-end | ✅ Purchase → cancel → expiry lifecycle tested locally | Sandbox run of RUNBOOK §5 steps 1–4 on the VPS, screenshots | F → PM |
| 3 | Match-day collection unattended | ✅ Cron schedule, lock, logs, optional pings | Install crontab; 2 match weekends without manual runs | F |
| 4 | Automated `two_up.db` backup | ✅ Nightly + post-live + before train/historical/`--force`; restore command | First backup; **restore drill**; off-box copy | F |
| 5 | Fresh opportunities, no stale junk | ✅ Finished matches never served; kicked-off games dropped from cache | Spot-check list on 3 match days (dupes, sensible %) | PM |
| 6 | Paper log running | ✅ Scheduled open + settle for FTA / Early / Chaos | 2+ weeks of settled rows, reviewed weekly | PM |
| 7 | App loads Pro / Opportunities / Early / Chaos | ⚠️ App code not in this repo — see app blockers below | TestFlight pass on a clean device | F |
| 8 | Disclaimer copy | ⚠️ App-side | Copy approved per messaging guardrails | PM |

### P0 actions before anything else

- [ ] **Rotate** the API-Football and TheStatsAPI keys (the old ones are in git history) and put the new ones in `/etc/turnaroundiq.env`
- [ ] `python -u run.py backup --label first` → then do the restore drill
- [ ] `crontab deploy/crontab.example`
- [ ] Record current counts from `python -u run.py health` here: match_results `__` · team_stats `__` · training_data `__` · model present `__`

### App blockers found in `frontend/lib/apiClient.js` / `app.jsx`

- `API_BASE` defaults to `http://<VPS IP>:8080` — plain HTTP; switch to the HTTPS domain for release.
- `getAppUserId()` falls back to `"dev_user"` — every fresh install would share one account (and its Pro status, if `dev_user` was ever marked Pro). Must use `Purchases.appUserID`.
- The API trusts the bearer app user ID as-is. Fine with RevenueCat's random anonymous IDs; **not** fine if IDs are emails/usernames.
- `app.jsx` calls `GET /model/runs`, which the API does not serve.

## Should-have

- [ ] Walk-forward / calibration notes in plain language
- [ ] League baseline context on opportunities (FTA% vs league)
- [x] Runbook: restart API, live, train, restore — `deploy/RUNBOOK.md`
- [ ] Domain + HTTPS (`deploy/CADDY.md`)

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
