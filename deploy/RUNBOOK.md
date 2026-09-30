# TurnaroundIQ runbook

Everything the founder / on-call needs to run, check, and recover the backend.
Paths assume the repo is at `/root/TurnaroundIQ` with a `venv/`.

## 0. One-time setup (single-line commands, safe to re-run)

Each line is independent — paste one at a time. If SSH drops mid-way, reconnect
and paste the same line again.

```bash
cd ~/TurnaroundIQ && git pull
bash deploy/set_env.sh API_FOOTBALL_KEY <new key>
bash deploy/set_env.sh THESTATSAPI_KEY <new key>
bash deploy/set_env.sh REVENUECAT_SECRET_API_KEY <sk_ key>
bash deploy/set_env.sh REVENUECAT_WEBHOOK_AUTH $(openssl rand -hex 24)
bash deploy/set_env.sh --show
tmux new -d -s setup 'bash deploy/setup_server.sh --cron'
tail -n 30 logs/setup.log
```

`setup_server.sh` installs the API as a systemd service, installs Caddy for
HTTPS, opens ports 80/443, installs the crontab (`--cron`), and checks
`https://<domain>/health`. It runs inside tmux, so a dropped connection doesn't
stop it; re-check with the `tail` line until it prints `SETUP DONE`.

The API-Football / TheStatsAPI keys were removed from `constants.py` —
**rotate them** (the old ones are in git history).

Long jobs — run detached, then check the log:

```bash
tmux new -d -s job 'cd ~/TurnaroundIQ && venv/bin/python -u run.py historical > logs/job.log 2>&1'
tail -n 20 ~/TurnaroundIQ/logs/job.log
```

## 1. API (production path: systemd + Caddy)

```bash
sudo cp deploy/turnaroundiq-api.service /etc/systemd/system/
sudo systemctl daemon-reload
tmux kill-session -t api 2>/dev/null     # stop the old tmux API
sudo systemctl enable --now turnaroundiq-api
sudo systemctl status turnaroundiq-api
journalctl -u turnaroundiq-api -f        # logs
sudo systemctl restart turnaroundiq-api  # restart
```

HTTPS: follow `deploy/CADDY.md`, then point the app's `NEXT_PUBLIC_API_BASE`
and the RevenueCat webhook at `https://api.turnaroundiq.co.uk`.

`run.py api` (tmux, `0.0.0.0:8080`, plain HTTP) is for testing only.

### Health

```bash
curl -s http://127.0.0.1:8080/health | python -m json.tool
```

| HTTP | `status` | Meaning |
|---|---|---|
| 200 | `ok` | Healthy |
| 200 | `degraded` | Serving, but see `warnings` (stale results, old backup, missing key) |
| 503 | `critical` | Cannot serve real intel — empty/missing DB or no model. **Restore (section 4).** |

`fixture_source` on `/health` and `/opportunities`:
`api-football-upcoming` (fresh) · `cached-upcoming` (API-Football failing,
serving last good list minus kicked-off games) · `unavailable` (nothing to show —
check key/quota; finished matches are never shown as upcoming).

## 2. Schedule

```bash
crontab deploy/crontab.example     # installs all jobs
crontab -l
tail -f logs/live.log              # each job logs to logs/<name>.log
```

| Job | When (UTC) | What |
|---|---|---|
| live | every 3h + 06:40 with odds | results → team stats; backup on success |
| paper | 09:00, 15:00 | open paper picks for FTA / Early / Chaos (`PAPER_USER`) |
| paper-settle | every 3h | settle finished paper picks |
| backup | 03:30 | nightly backup |
| backfill | 01:15 | TheStatsAPI history, up to 1500 matches/night, resumes |
| historical | Sun 04:40 | rebuild historical profiles from collected CSVs |
| health | every 30 min | exit 1 degraded / 2 critical |

Optional alerting: create free checks at healthchecks.io and set
`HEALTHCHECK_URL_LIVE`, `_BACKUP`, `_PAPER`, `_HEALTH` in the env file.
A missed or failed run then emails/pings you.

API quota: scheduled live runs use `RESULTS_LOOKBACK_DAYS=3`. A full-season
sweep (`python -u collectors/results_collector.py --days 75`) is manual only.

## 3. Data jobs

```bash
python -u run.py live            # results + team stats (+ odds); backs up after success
python -u run.py historical      # backs up first
python -u run.py walk-forward    # check before retraining
python -u run.py train           # backs up first; refuses to retrain on empty training_data
```

After any major job, report: `python -u run.py health` (row counts) and
`python -u run.py backup --list` (dated backup exists).

### First run with a TheStatsAPI key

```bash
python -u collectors/backfill_thestatsapi.py --probe
```

Prints raw competition / season / match / timeline responses for the Premier
League and ends with `check: OK` if the parser reads them correctly. If it
shows `timeline_x-y_vs_final_a-b` or `goal_team_unmatched`, send the output
to eng before running the full backfill. Then do a small trial:

```bash
python -u run.py historical --league "Premier League" --season 2024 --max-matches 400
python -u run.py health
```

## 4. Backup + restore

Backups: `backups/two_up-<UTC timestamp>-<label>.db`, last `BACKUP_KEEP` (30)
kept. An empty-looking backup never prunes older ones.

```bash
python -u run.py backup --list                       # pick a good one (row counts shown)
sudo systemctl stop turnaroundiq-api
python -u run.py restore backups/two_up-YYYYMMDD-HHMMSS-label.db
                                                      # current DB saved as *-pre-restore.db first
sudo systemctl start turnaroundiq-api
python -u run.py health
```

**Off-box copy (do this):** backups on the same VPS do not survive losing the
VPS. Add a daily copy, for example:

```bash
# 45 3 * * *  rsync -a /root/TurnaroundIQ/backups/ user@other-host:tiq-backups/
```

**Restore drill (P0 gate):** once, on purpose — take a backup, restore it,
confirm `/health` is `ok` and row counts match. Record the date in the launch gate.

## 5. RevenueCat end-to-end check

```bash
curl -s -H "Authorization: Bearer <sandbox appUserID>" https://api.turnaroundiq.co.uk/me
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer <sandbox appUserID>" https://api.turnaroundiq.co.uk/opportunities
```

1. Fresh sandbox user → `/opportunities` = **402**, `/me.entitled=false`
2. Sandbox purchase in TestFlight → webhook arrives
   (`sqlite3 two_up.db "SELECT * FROM subscribers"`) → **200**, `entitled=true`
3. Cancel → still **200** until `expires_at`
4. After sandbox expiry (minutes) → **402**, app shows paywall

## 6. Incidents

| Symptom | First action |
|---|---|
| `/health` 503 `match_results_empty` | Stop API, restore latest good backup (section 4) |
| `results_stale` warning | `tail -100 logs/live.log`; check key/quota; run `run.py live` by hand |
| `fixture_source: unavailable` | API-Football key/quota; opportunities list is empty until fixed |
| 500 on `/opportunities` | `journalctl -u turnaroundiq-api -n 200` (details are logged, not sent to the app) |
| Wrong/empty DB after a manual script | DB path is now absolute (`TURNAROUNDIQ_DB` to override); restore if needed |
