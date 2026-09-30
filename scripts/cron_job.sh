#!/usr/bin/env bash
# Run one scheduled job with a lock, a log file and an optional ping.
#
#   scripts/cron_job.sh <name> <command...>
#   scripts/cron_job.sh live python -u run.py live --skip-odds
#
# - flock: a slow run never overlaps the next one
# - logs:  logs/<name>.log (rotated at ~5MB)
# - ping:  $HEALTHCHECK_URL_<NAME> on success, <url>/fail on failure
set -uo pipefail

NAME="$1"; shift
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f /etc/turnaroundiq.env ]; then
  set -a; . /etc/turnaroundiq.env; set +a
fi

if [ -x "$ROOT/venv/bin/python" ]; then
  export PATH="$ROOT/venv/bin:$PATH"
fi

mkdir -p logs
LOG="logs/${NAME}.log"
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 5000000 ]; then
  mv "$LOG" "$LOG.1"
fi

exec 9>"logs/${NAME}.lock"
if ! flock -n 9; then
  echo "[$(date -u +%FT%TZ)] $NAME already running — skipped" >>"$LOG"
  exit 0
fi

echo "[$(date -u +%FT%TZ)] START $NAME: $*" >>"$LOG"
"$@" >>"$LOG" 2>&1
CODE=$?
echo "[$(date -u +%FT%TZ)] END $NAME exit=$CODE" >>"$LOG"

VAR="HEALTHCHECK_URL_$(echo "$NAME" | tr '[:lower:]-' '[:upper:]_')"
URL="${!VAR:-}"
if [ -n "$URL" ]; then
  if [ "$CODE" -eq 0 ]; then
    curl -fsS -m 10 --retry 3 "$URL" >/dev/null 2>&1 || true
  else
    curl -fsS -m 10 --retry 3 "$URL/fail" >/dev/null 2>&1 || true
  fi
fi
exit "$CODE"
