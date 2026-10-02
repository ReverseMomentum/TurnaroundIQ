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

HOSTS = ("https://promo.betfair.com", "https://www.betfairpromo.com")
PATH = "/betfairsp/prices/dwbfprices{region}{market}{d}.csv"
CACHE = ROOT / "data" / "bsp"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept": "text/csv,text/plain,*/*"}
_failures = []


def fetch(region, market, day):
    """Cached download; only real CSVs are cached, so a failed day is retried next run."""
    d = day.strftime("%d%m%Y")
    path = CACHE / f"{region}{market}{d}.csv"
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(errors="replace")
    for host in HOSTS:
        url = host + PATH.format(region=region, market=market, d=d)
        try:
            r = requests.get(url, timeout=30, headers=HEADERS)
        except requests.RequestException as e:
            _failures.append(f"{url}: {type(e).__name__}: {e}"[:200])
            continue
        finally:
            time.sleep(0.3)
        if r.status_code == 200 and "EVENT_ID" in r.text[:300].upper():
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(r.text)
            return r.text
        _failures.append(f"{url}: HTTP {r.status_code}, {r.headers.get('content-type')}, "
                         f"starts {r.text[:80]!r}")
    return ""


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
        print("no files downloaded. First failures:")
        for f in _failures[:4]:
            print("  " + f)
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
