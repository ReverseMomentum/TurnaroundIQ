#!/usr/bin/env python3
"""
The Stables: what is live in the model right now.

    venv/bin/python scripts/stables_status.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from racing import store  # noqa: E402


def main():
    cal = store.latest_calibration()
    blend = cal.get("blend") or {}
    recal = cal.get("recal") or {}
    print(f"calibration saved: {cal.get('created_at') or 'never'} (source: {cal.get('source') or '-'})")
    print(f"position curves fitted: {'yes' if cal.get('fitted') else 'no (defaults)'}"
          f", on {cal.get('n_races') or 0} races; per race type / field size: {len(cal.get('segment_discounts') or {})}")
    if blend.get("fitted"):
        feats = (blend.get("features") or [])[1:]
        print(f"ranking model (form, ratings, connections...): LIVE, {blend.get('kind') or 'blend'}, "
              f"features: {', '.join(feats) or '-'}")
    else:
        print("ranking model (form, ratings, connections...): NOT live - prices only")
    if recal.get("fitted"):
        print(f"place calibration: LIVE, fitted on {recal.get('n_rows')} runner rows, "
              f"source: {recal.get('source') or 'kaggle (learning run)'}"
              + (f", last BSP refit {cal['recal_bsp_at']}" if cal.get("recal_bsp_at") else ""))
    else:
        print("place calibration: NOT live")
    print(f"price estimate margin per runner: {cal.get('best_price_rate') or 'default 0.015 (not enough bets yet)'}")
    log = ROOT / "logs" / "stables_recal_bsp.json"
    if log.exists():
        r = json.loads(log.read_text())
        print(f"last BSP refit run: test from {r.get('test_from')}, beat live: {r.get('better')}, scores {r.get('scores')}")
    else:
        print("last BSP refit run: none on file")
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        print("weekly refit in crontab:", "yes" if "stables_recal_bsp" in cron else "NO")
    except OSError:
        print("weekly refit in crontab: could not read crontab")


if __name__ == "__main__":
    main()
