# TurnaroundIQ — context for a new chat

Read this first. It is what a fresh session needs to work on this repo.

## The founder and how they work
- Solo founder. Works only from an iPhone, using Termius over SSH to a Contabo VPS.
- **Every VPS command must be one single copy-pastable line.** Never a multi-line
  heredoc or a multi-line `python -c`. If it needs more than one line, write it as
  a script in the repo.
- Pushing straight to `main` is authorised. Deploying on the VPS means
  `cd ~/TurnaroundIQ && git pull -q origin main && ...`.
- **Wording must stay honest:** no profit claims, no "predicts", no "high
  confidence", no guarantees. Say 18+ and BeGambleAware wherever relevant. These
  match the UK ad rules (CAP code section 16 and the ASA's tipster guidance).
- Never put model identifiers in commits or code.

## Stack
- **API:** FastAPI app in `api/app.py`, run by systemd as `turnaroundiq-api`.
- **Data:** SQLite, `two_up.db`.
- **Web server:** Caddy.
- **Scheduled jobs:** cron through `scripts/cron_job.sh <name> <cmd>`, which takes a
  flock lock in `logs/<name>.lock`. The jobs are listed in `deploy/crontab.example`.
- **Secrets:** `/etc/turnaroundiq.env`, set with `bash deploy/set_env.sh KEY VALUE`.
- **Web app:** Vite + React in `mobile/`.
  - Deploy with `bash deploy/build_web.sh`.
  - Almost all of the UI is in `mobile/src/App.jsx`.
  - API calls live in `mobile/src/lib/api.js`.
- **Billing:**
  - RevenueCat Web Billing with Stripe; the entitlement is `pro`.
  - In code, `require_pro()` in `api/app.py` gates paid features.
  - The free beta (`billing/beta.py`, env `BETA_FREE_UNTIL`) counts as Pro until it ends.
- **Tests:** run with `python -m pytest -q`. They must all pass before pushing.

## Design system (App.jsx)
- **Style values:** `c` (colours), `card`, `heroCard`, `accentCard`, `primaryBtn`, `chip()`.
- **Components:** `PageShell`, `PageTitle`, `SectionLabel`, `BigNum`, `Bar`, `Sheet`,
  `NumField`, `ScoreBox`, `Paywall`, `Loading`, `ErrorBox`, `Disclaimer`, `BetaBanner`.
- **Look:** dark premium theme with the Inter font. On desktop (1024px and wider)
  there is a sidebar and tables replace cards.
- **Navigation:** `NAV_MAIN` and `NAV_MORE` in App.jsx. A new product (e.g. "The
  Stables") is a new entry there, plus a page component in the same style.

## Existing product (football)
- **FTA model** (`models/fta_path_model.py`):
  - FTA% = P(team goes 2 up) × P(fails to win once 2 up).
  - Inputs are built only from earlier matches (no look-ahead).
  - Calibrated, with recency weighting.
  - 28 leagues, including the youth leagues PL2 (702) and PDL (703) and the Eerste Divisie (89).
- **Odds** (`collectors/odds_apisports.py`):
  - Best UK back price per side.
  - Estimated lay = fair price plus one Betfair tick.
  - Refreshed by a 24h-window cron job, plus an in-app refresh button.
- **Other pages:** Early Goal Hunter, Chaos Factor, the bet tracker (paper P/L) and the calculator.

## The Stables (horse racing extra places)
- Not a winner model: estimates P(finish k-th) for every runner and compares the
  chance of landing in a bookmaker's paid places (incl. extra places) with what the
  each-way terms imply. Code in `racing/`, API in `api/stables.py` (`/stables/races`,
  `/stables/price`, Pro), page in `mobile/src/stables/StablesPage.jsx` (gets the
  design system from App.jsx as the `ui` prop).
- Model: win prices de-vigged (power method; exchange mid if every runner has one)
  -> discounted Plackett-Luce/Harville, 10,000 Monte Carlo races -> P1..P9 ->
  each-way EV, edge, 0-100 confidence, robust ¼ Kelly, grade A-D. Grade A is held
  back until the discounts are fitted on results.
- Data: no feed yet. Load JSON cards with `scripts/stables_import.py <file>` (format in
  its docstring). Results in the same file feed `scripts/stables_calibrate.py`.
  `scripts/stables_run.py [date]` stores predictions/opportunities. Tables are `rac_*`
  in two_up.db. The app also has a "Price a race" form for typing a race in by hand.
- Free checks (no racing subscription): `scripts/stables_kaggle_check.py` fits on
  Kaggle results up to a year and tests on later years (`--peek` shows column
  matching, `--save` stores the fit for the app); `scripts/stables_bsp_check.py
  FROM TO` scores P(top k) on recent races from Betfair's free BSP files (Betfair
  returns 403 to the VPS, so this one is parked).
- Calibration (saved by `--save`) holds: position discounts, non-finish rates by
  race type and price (`racing/nonfinish.py`; fallers can't place), and an edge
  shrink fitted on training races so the EV shown matches past results.

## Working alongside other chats
More than one chat may push to `main`. Pull before starting. Keep new work in new
files where possible, so two chats aren't both editing `App.jsx` at the same time.
