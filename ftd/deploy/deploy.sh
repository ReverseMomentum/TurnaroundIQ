#!/usr/bin/env bash
# Build the FTD site and (re)start the waitlist API. Safe to re-run.
#   bash ftd/deploy/deploy.sh
set -euo pipefail
FTD="$(cd "$(dirname "$0")/.." && pwd)"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
WEB_DIR=/var/www/ftd

cd "$FTD"
echo "[ftd] installing packages"
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci --no-audit --no-fund --loglevel=error
echo "[ftd] building"
npx vite build --logLevel warn

$SUDO mkdir -p "$WEB_DIR"
$SUDO rm -rf "$WEB_DIR.new" && $SUDO cp -r dist "$WEB_DIR.new"
$SUDO rm -rf "$WEB_DIR.old" && { [ -d "$WEB_DIR" ] && $SUDO mv "$WEB_DIR" "$WEB_DIR.old" || true; }
$SUDO mv "$WEB_DIR.new" "$WEB_DIR"
$SUDO chmod -R a+rX "$WEB_DIR"

python3 -c "import fastapi, uvicorn, requests" 2>/dev/null || pip install -q fastapi uvicorn requests
[ -f /etc/ftd.env ] || { $SUDO cp deploy/ftd.env.example /etc/ftd.env; $SUDO chmod 600 /etc/ftd.env; echo "[ftd] created /etc/ftd.env from the example"; }
sed "s#/root/TurnaroundIQ/ftd#$FTD#" deploy/ftd-waitlist.service | $SUDO tee /etc/systemd/system/ftd-waitlist.service >/dev/null
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now ftd-waitlist >/dev/null
$SUDO systemctl restart ftd-waitlist
sleep 2
curl -fsS http://127.0.0.1:8090/api/health && echo
$SUDO systemctl reload caddy 2>/dev/null || true
echo "[ftd] done. Site files: $WEB_DIR. Add deploy/Caddyfile.ftd to Caddy once (see ftd/README.md)."
