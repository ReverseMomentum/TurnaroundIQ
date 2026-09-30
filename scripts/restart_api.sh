#!/usr/bin/env bash
# Restart TurnaroundIQ API in a detached tmux session named "api".
# Usage: bash scripts/restart_api.sh
#    or: python -u run.py api

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${API_PORT:-8080}"
HOST="${API_HOST:-127.0.0.1}"
SESSION="${API_TMUX_SESSION:-api}"

# Production: systemd service behind Caddy. Restart that instead of starting
# a second copy in tmux (which would fight it for the port).
if systemctl list-unit-files turnaroundiq-api.service 2>/dev/null | grep -q enabled; then
  echo "[api] restarting systemd service turnaroundiq-api"
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO systemctl restart turnaroundiq-api
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health" || true)"
    case "$code" in 200|503) break;; esac
    sleep 1
  done
  echo "[api] health: HTTP ${code:-000} (200 ok, 503 = data critical, 000 = not up: journalctl -u turnaroundiq-api -n 50)"
  exit 0
fi

echo "[api] root=$ROOT port=$PORT session=$SESSION"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "[api] WARNING bound to 0.0.0.0 — plain HTTP, reachable from the internet."
  echo "[api]         Production path: systemd + Caddy (deploy/RUNBOOK.md), API_HOST=127.0.0.1"
fi

# Free the port if something is already bound
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
elif command -v lsof >/dev/null 2>&1; then
  pids=$(lsof -t -i:":$PORT" 2>/dev/null || true)
  if [ -n "${pids:-}" ]; then
    kill $pids 2>/dev/null || true
  fi
fi
sleep 1

# Prefer project venv uvicorn
if [ -x "$ROOT/venv/bin/uvicorn" ]; then
  UVICORN="$ROOT/venv/bin/uvicorn"
elif [ -x "$ROOT/venv/bin/python" ]; then
  UVICORN="$ROOT/venv/bin/python -m uvicorn"
else
  UVICORN="python3 -m uvicorn"
fi

CMD="cd '$ROOT' && $UVICORN api.app:app --host $HOST --port $PORT"

# Replace existing session if present
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[api] killing existing tmux session '$SESSION'"
  tmux kill-session -t "$SESSION" || true
  sleep 0.5
fi

tmux new-session -d -s "$SESSION" "$CMD"
echo "[api] started in tmux session '$SESSION'"
echo "[api] attach: tmux attach -t $SESSION"
echo "[api] health: curl -s http://127.0.0.1:${PORT}/health"

sleep 1
if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "[api] health OK"
else
  echo "[api] health not ready yet — check: tmux attach -t $SESSION"
fi
