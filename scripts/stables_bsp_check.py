#!/usr/bin/env python3
"""
The Stables: free check on recent races with Betfair's BSP files.

Downloads the daily UK + Irish win and "To Be Placed" BSP files (cached in
data/bsp/), takes win probabilities from the win BSP, and scores the model's
P(top k) against who actually placed, for every places-paid value k found
(2, 3, and 4+ where Betfair ran extra-place markets). The place market's own
BSP is scored on the same runners as a benchmark.

    venv/bin/python scripts/stables_bsp_check.py 2025-09-01 2025-09-30
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from racing import backtest, positions, store  # noqa: E402

URL = "https://promo.betfair.com/betfairsp/prices/dwbfprices{region}{market}{d}.csv"
CACHE = ROOT / "data" / "bsp"


def fetch(region, market, day):
    d = day.strftime("%d%m%Y")
    path = CACHE / f"{region}{market}{d}.csv"
    if path.exists():
        return path.read_text(errors="replace")
    r = requests.get(URL.format(region=region, market=market, d=d), timeout=30,
                     headers={"User-Agent": "Mozilla/5.0 TurnaroundIQ research"})
    time.sleep(0.3)
    text = r.text if r.status_code == 200 and "EVENT_ID" in r.text[:200].upper() else ""
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    start, end = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
    races, day = [], start
    while day <= end:
        for region in ("uk", "ire"):
            win, place = fetch(region, "win", day), fetch(region, "place", day)
            if win and place:
                races.extend(backtest.bsp_races(win, place))
        day += timedelta(days=1)
    print(f"{len(races)} races with full win + place BSP, {start} to {end}")
    if not races:
        print("no files: check the dates, or that promo.betfair.com is reachable")
        sys.exit(1)
    sets = {"prior": list(positions.DEFAULT_DISCOUNTS), "harville": [1.0]}
    cal = store.latest_calibration()
    if cal.get("fitted"):
        sets["fitted"] = cal["discounts"]
    report = backtest.bsp_check(races, sets)
    for k, models in report.items():
        n = next(iter(models.values()))["n"]
        print(f"\n{k} ({n} runners; lower is better)")
        for label, s in models.items():
            print(f"  {label:<17} brier {s['brier']:.5f}  log loss {s['log_loss']:.4f}  ECE {s['calibration_error']:.4f}"
                  f"  predicted {s['mean_predicted']:.3f}  actual {s['observed_rate']:.3f}")
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stables_bsp_check.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
