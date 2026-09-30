#!/usr/bin/env bash
# Build the web app and publish it at https://app.turnaroundiq.co.uk
# Safe to re-run (e.g. after every git pull that changes mobile/).
#   bash deploy/build_web.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
WEB_DIR=/var/www/turnaroundiq-app

if ! command -v node >/dev/null || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 20 ]; then
  echo "[web] installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO bash - >/dev/null
  $SUDO apt-get install -y -qq nodejs
fi

cd "$ROOT/mobile"
echo "[web] installing packages"
npm ci --no-audit --no-fund --loglevel=error
echo "[web] building"
VITE_API_BASE="${VITE_API_BASE:-https://api.turnaroundiq.co.uk}" npx vite build --logLevel warn

$SUDO mkdir -p "$WEB_DIR"
$SUDO rm -rf "$WEB_DIR.new" && $SUDO cp -r dist "$WEB_DIR.new"
$SUDO rm -rf "$WEB_DIR.old" && { [ -d "$WEB_DIR" ] && $SUDO mv "$WEB_DIR" "$WEB_DIR.old" || true; }
$SUDO mv "$WEB_DIR.new" "$WEB_DIR"
$SUDO chmod -R a+rX "$WEB_DIR"

$SUDO cp "$ROOT/deploy/Caddyfile" /etc/caddy/Caddyfile
$SUDO systemctl reload caddy || $SUDO systemctl restart caddy
sleep 3
code=$(curl -s -o /dev/null -w '%{http_code}' https://app.turnaroundiq.co.uk/ || true)
echo "[web] https://app.turnaroundiq.co.uk -> HTTP $code (200 = live; 000 = DNS/cert not ready yet)"
