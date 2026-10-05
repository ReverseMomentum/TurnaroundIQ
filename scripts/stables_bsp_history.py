#!/usr/bin/env python3
"""
The Stables: fill rac_history with recent races from Betfair's free daily BSP
files (racing/bsp_files.py), so today's runners have course / distance /
"placed vs prices" records. The Kaggle data stops in 2020 and our own Betfair
results only start when the collector did.

Run it through scripts/cron_job.sh so it picks up BETFAIR_PROXY (Betfair
refuses non-UK servers):

    scripts/cron_job.sh bsphistory python -u scripts/stables_bsp_history.py
    scripts/cron_job.sh bsphistory python -u scripts/stables_bsp_history.py --since 2023-01-01

Defaults: from the day after the last Kaggle race on file (else 2021-01-01) to
the day before our own Betfair results start (else yesterday). Files are cached
in data/bsp/, so a stopped run carries on where it left off. Roughly 4 files a
day: about 1-3 hours for five years.
"""
import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import get_db  # noqa: E402
from racing import bsp_files, store  # noqa: E402


def _bounds():
    conn = get_db()
    try:
        store.ensure_tables(conn)
        last_kaggle = conn.execute("SELECT MAX(date) FROM rac_history WHERE source = 'kaggle'").fetchone()[0]
        first_live = conn.execute("SELECT MIN(date) FROM rac_history WHERE source = 'betfair'").fetchone()[0]
    finally:
        conn.close()
    start = date.fromisoformat(last_kaggle[:10]) + timedelta(days=1) if last_kaggle else date(2021, 1, 1)
    end = date.fromisoformat(first_live[:10]) - timedelta(days=1) if first_live else date.today() - timedelta(days=1)
    return start, end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat)
    ap.add_argument("--until", type=date.fromisoformat)
    a = ap.parse_args()
    start, end = _bounds()
    start, end = a.since or start, a.until or end
    proxy = os.environ.get("BETFAIR_PROXY", "").strip()
    print(f"BSP history {start} to {end}, {'via ' + proxy if proxy else 'no proxy (BETFAIR_PROXY not set)'}", flush=True)
    day, month, races, runners, empty_days = start, None, 0, 0, 0
    while day <= end:
        found = False
        for region in ("uk", "ire"):
            win = bsp_files.fetch(region, "win", day)
            if not win:
                continue
            found = True
            rows = bsp_files.history_rows(win, bsp_files.fetch(region, "place", day))
            if rows:
                store.add_history(rows)
                races += len({r["race_ref"] for r in rows})
                runners += len(rows)
        empty_days = 0 if found else empty_days + 1
        if empty_days == 10 and day - start < timedelta(days=10):
            print("no files for the first 10 days. First failures:")
            for f in bsp_files.failures[:4]:
                print("  " + f)
            print("HTTP 403: run it through scripts/cron_job.sh so BETFAIR_PROXY (the UK link) is used.")
            sys.exit(1)
        if day.strftime("%Y-%m") != month and month is not None:
            print(f"  {month}: {races} races, {runners} runners so far", flush=True)
        month = day.strftime("%Y-%m")
        day += timedelta(days=1)
    print(f"done: {races} races, {runners} runner rows added to rac_history", flush=True)
    if not races and bsp_files.failures:
        print("nothing downloaded. First failures:", *bsp_files.failures[:3], sep="\n  ")


if __name__ == "__main__":
    main()
