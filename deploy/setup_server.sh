#!/usr/bin/env bash
# One-shot, re-runnable server setup: API on systemd + Caddy HTTPS + firewall.
# Safe to run again if the SSH connection dropped halfway.
#
#   bash deploy/setup_server.sh              # API + HTTPS
#   bash deploy/setup_server.sh --cron       # also install the crontab
#
# Output is also written to logs/setup.log.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
exec > >(tee -a logs/setup.log) 2>&1
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
DOMAIN="$(awk '/^[a-z0-9.-]+ *\{/{print $1; exit}' deploy/Caddyfile)"
ENV_FILE=/etc/turnaroundiq.env
say() { echo; echo "=== $* ==="; }
fail=0
failed=""

say "1/6 env file"
if [ ! -f "$ENV_FILE" ]; then
  echo "MISSING $ENV_FILE — run: bash deploy/set_env.sh API_FOOTBALL_KEY <key>"
  fail=1; failed="$failed env"
elif ! $SUDO grep -qE '^API_FOOTBALL_KEY=.+' "$ENV_FILE"; then
  echo "WARNING API_FOOTBALL_KEY empty in $ENV_FILE (collectors will stop)"
else
  echo "ok"
fi

say "2/6 python venv + requirements"
[ -x venv/bin/python ] || python3 -m venv venv
venv/bin/pip install -q -r requirements.txt && echo "ok" || { echo "pip install failed"; fail=1; failed="$failed python-deps"; }

say "3/6 API service (systemd, 127.0.0.1:8080)"
tmux kill-session -t api 2>/dev/null && echo "stopped old tmux API" || true
sed "s#/root/TurnaroundIQ#$ROOT#g" deploy/turnaroundiq-api.service | $SUDO tee /etc/systemd/system/turnaroundiq-api.service >/dev/null
$SUDO systemctl daemon-reload
$SUDO systemctl enable turnaroundiq-api >/dev/null 2>&1
$SUDO systemctl restart turnaroundiq-api
sleep 4
if curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health | grep -qE '200|503'; then
  echo "ok — API answering locally"
else
  echo "API not answering — see: journalctl -u turnaroundiq-api -n 50"; fail=1; failed="$failed api"
fi

say "4/6 Caddy (HTTPS for $DOMAIN)"
if ! command -v caddy >/dev/null; then
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | $SUDO gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | $SUDO tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq caddy
fi
$SUDO mkdir -p /var/log/caddy && $SUDO chown caddy:caddy /var/log/caddy 2>/dev/null || true
$SUDO cp deploy/Caddyfile /etc/caddy/Caddyfile
$SUDO systemctl enable caddy >/dev/null 2>&1
$SUDO systemctl restart caddy && echo "ok" || { echo "caddy failed — journalctl -u caddy -n 50"; fail=1; failed="$failed caddy"; }

say "5/6 firewall"
if command -v ufw >/dev/null && $SUDO ufw status | grep -q "Status: active"; then
  $SUDO ufw allow 22/tcp >/dev/null
  $SUDO ufw allow 80/tcp >/dev/null
  $SUDO ufw allow 443/tcp >/dev/null
  echo "ok — 22/80/443 open"
else
  echo "ufw not active — nothing to change (check Contabo firewall allows 80/443)"
fi

if [ "${1:-}" = "--cron" ]; then
  say "cron"
  sed "s#/root/TurnaroundIQ#$ROOT#g" deploy/crontab.example | crontab - && echo "ok — crontab installed" || { fail=1; failed="$failed cron"; }
fi

say "6/6 HTTPS check (certificate can take ~1 min first time)"
code=000
for i in 1 2 3 4 5 6; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/health" || true)"
  case "$code" in 200|503) break;; esac
  sleep 10
done
case "$code" in
  200) echo "ok — https://$DOMAIN/health is healthy";;
  503) echo "HTTPS works; health is critical (data) — run: venv/bin/python run.py health";;
  *)   echo "HTTPS not ready (code $code). Check Cloudflare record is DNS only (grey), then: journalctl -u caddy -n 50"; fail=1; failed="$failed https";;
esac

echo
[ "$fail" -eq 0 ] && echo "SETUP DONE" || echo "SETUP FINISHED WITH ISSUES:$failed (details above, full log: logs/setup.log)"
exit "$fail"
