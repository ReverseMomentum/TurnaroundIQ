# TurnaroundIQ runbook

Everything the founder / on-call needs to run, check, and recover the backend.
Paths assume the repo is at `/root/TurnaroundIQ` with a `venv/`.

## 0. One-time setup (after pulling this change)

```bash
cd /root/TurnaroundIQ && git pull
source venv/bin/activate && pip install -r requirements.txt

# Secrets live outside git. API keys were removed from constants.py —
# ROTATE the old API-Football + TheStatsAPI keys (they are in git history).
sudo cp deploy/env.example /etc/turnaroundiq.env
sudo chmod 600 /etc/turnaroundiq.env
sudo nano /etc/turnaroundiq.env        # fill in the new keys + RevenueCat

python -u run.py health                 # expect row counts, no *_key_missing
python -u run.py backup --label first   # first dated backup
```

Until `/etc/turnaroundiq.env` exists, collectors exit with
`API_FOOTBALL_KEY is not set` and `/opportunities` returns no fixtures.

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
and the RevenueCat webhook at `https://api.<domain>`.

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
curl -s -H "Authorization: Bearer <sandbox appUserID>" https://api.<domain>/me
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer <sandbox appUserID>" https://api.<domain>/opportunities
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
