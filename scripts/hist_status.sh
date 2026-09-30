#!/usr/bin/env bash
# Compact historical-backfill status for a phone screen.
#   bash scripts/hist_status.sh
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "code:     $(git log -1 --format='%h %s' | cut -c1-60)"
if tmux has-session -t hist 2>/dev/null; then echo "running:  yes (tmux hist)"; else echo "running:  no"; fi
done_n=$( [ -f data/apisports_done.csv ] && tail -n +2 data/apisports_done.csv | wc -l || echo 0)
coll_n=$( [ -f data/ginf_apisports.csv ] && tail -n +2 data/ginf_apisports.csv | wc -l || echo 0)
skip_n=$( [ -f data/apisports_skipped.csv ] && tail -n +2 data/apisports_skipped.csv | wc -l || echo 0)
echo "seasons:  $done_n / 125 complete"
echo "matches:  $coll_n collected, $skip_n rejected"
LOG=logs/historical.log
if [ -f "$LOG" ]; then
  echo "--- last lines of $LOG ---"
  grep -vE '^\s+\^+\s*$' "$LOG" | tail -n 8 | cut -c1-110
fi
