#!/usr/bin/env bash
# Set one value in /etc/turnaroundiq.env (creates it from env.example if missing).
#   bash deploy/set_env.sh API_FOOTBALL_KEY abc123
#   bash deploy/set_env.sh --show        # list keys set (values hidden)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${TURNAROUNDIQ_ENV_FILE:-/etc/turnaroundiq.env}"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

if [ ! -f "$ENV_FILE" ]; then
  $SUDO cp "$ROOT/deploy/env.example" "$ENV_FILE"
  echo "[env] created $ENV_FILE from env.example"
fi
$SUDO chmod 600 "$ENV_FILE"

if [ "${1:-}" = "--show" ]; then
  $SUDO grep -E '^[A-Z_]+=' "$ENV_FILE" | sed -E 's/=(.{0,4}).*/=\1… (set)/; s/=… \(set\)$/= (EMPTY)/'
  exit 0
fi

KEY="${1:?usage: set_env.sh KEY VALUE}"
VALUE="${2:?usage: set_env.sh KEY VALUE}"
case "$KEY" in *[!A-Z0-9_]*) echo "[env] bad key name: $KEY"; exit 1;; esac

TMP="$(mktemp)"
$SUDO grep -v -E "^#? *${KEY}=" "$ENV_FILE" > "$TMP" || true
printf '%s=%s\n' "$KEY" "$VALUE" >> "$TMP"
$SUDO cp "$TMP" "$ENV_FILE"; rm -f "$TMP"
$SUDO chmod 600 "$ENV_FILE"
echo "[env] $KEY set in $ENV_FILE"
