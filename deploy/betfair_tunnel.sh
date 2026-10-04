#!/usr/bin/env bash
# Route Betfair through a UK server (Betfair refuses this VPS's country).
#
#   bash deploy/betfair_tunnel.sh UK_SERVER_IP
#
# Run on the main VPS. Asks for the UK server's root password once (to install
# an SSH key), then:
#   - checks the UK server is in GB and can reach Betfair
#   - installs systemd service "betfair-tunnel": an SSH SOCKS link on
#     127.0.0.1:1080 that restarts itself if it drops
#   - installs PySocks, sets BETFAIR_PROXY, restarts the API
# Only the Betfair collector uses the link; nothing else changes.
set -euo pipefail
UK="${1:?usage: bash deploy/betfair_tunnel.sh UK_SERVER_IP}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY=/root/.ssh/betfair_uk
PORT=1080
say() { printf '\n[tunnel] %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
mkdir -p /root/.ssh && chmod 700 /root/.ssh
if [ ! -f "$KEY" ]; then
  say "creating SSH key $KEY"
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "turnaroundiq-betfair" >/dev/null
fi

say "installing the key on $UK (type the UK server's root password if asked)"
ssh-copy-id -i "$KEY.pub" -o StrictHostKeyChecking=accept-new "root@$UK"

SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "root@$UK")
say "checking the UK server"
country="$("${SSH[@]}" "curl -s https://ipinfo.io/country" || true)"
code="$("${SSH[@]}" "curl -s -o /dev/null -w '%{http_code}' -X POST https://identitysso.betfair.com/api/login -H 'X-Application: test' -H 'Accept: application/json'" || true)"
echo "  country: ${country:-unknown}   Betfair login page: HTTP ${code:-none}"
if [ "$code" != "200" ]; then
  echo "  Betfair does not answer this server with 200 either, so the link would not help. Stopping."
  exit 1
fi

say "installing systemd service betfair-tunnel"
cat > /etc/systemd/system/betfair-tunnel.service <<UNIT
[Unit]
Description=SSH SOCKS link to the UK server for Betfair (TurnaroundIQ)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N -D 127.0.0.1:$PORT -i $KEY -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new root@$UK
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now betfair-tunnel
sleep 3
systemctl is-active --quiet betfair-tunnel || { systemctl status betfair-tunnel --no-pager | tail -5; exit 1; }

say "testing Betfair through the link"
code="$(curl -s -o /dev/null -w '%{http_code}' --socks5-hostname 127.0.0.1:$PORT -X POST https://identitysso.betfair.com/api/login -H 'X-Application: test' -H 'Accept: application/json' || true)"
echo "  Betfair via UK: HTTP $code"
[ "$code" = "200" ] || { echo "  link is up but Betfair still refuses; stopping"; exit 1; }

say "installing PySocks and setting BETFAIR_PROXY"
"$ROOT/venv/bin/pip" install -q "PySocks>=1.7.1"
bash "$ROOT/deploy/set_env.sh" BETFAIR_PROXY "socks5h://127.0.0.1:$PORT"
bash "$ROOT/scripts/restart_api.sh" >/dev/null 2>&1 || true

say "done. Next: venv/bin/python collectors/betfair.py --check"
