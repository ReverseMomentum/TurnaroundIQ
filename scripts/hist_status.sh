#!/usr/bin/env bash
# Compact historical-backfill status for a phone screen.
#   bash scripts/hist_status.sh
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3; [ -x venv/bin/python ] && PY=venv/bin/python
echo "code:     $(git log -1 --format='%h %s' | cut -c1-60)"
if pgrep -f "backfill_apisports.py" >/dev/null; then echo "running:  YES"; else echo "running:  no (nightly at 01:15 UTC)"; fi
target=$($PY -c "from constants import SUPPORTED_LEAGUE_IDS as L; from collectors.backfill_apisports import DEFAULT_SEASONS as S; print(len(L) * S)" 2>/dev/null || echo "?")
done_n=$( [ -f data/apisports_done.csv ] && tail -n +2 data/apisports_done.csv | wc -l || echo 0)
coll_n=$( [ -f data/ginf_apisports.csv ] && tail -n +2 data/ginf_apisports.csv | wc -l || echo 0)
skip_n=$( [ -f data/apisports_skipped.csv ] && tail -n +2 data/apisports_skipped.csv | wc -l || echo 0)
echo "seasons:  $done_n / $target complete (some older seasons may not exist in api-sports)"
echo "matches:  $coll_n collected, $skip_n rejected"
for LOG in logs/backfill.log logs/historical.log; do
  if [ -f "$LOG" ]; then
    echo "--- last lines of $LOG ($(date -r "$LOG" '+%d %b %H:%M')) ---"
    grep -vE '^\s+\^+\s*$' "$LOG" | tail -n 6 | cut -c1-110
  fi
done
