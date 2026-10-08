#!/usr/bin/env python3
"""
The Stables: fill tracked bets' Betfair SP (for CLV) from the daily BSP files, and show
why any bet still has none. Run through cron_job.sh so it uses the UK link:

    scripts/cron_job.sh bspfill python -u scripts/stables_bet_sp.py --days 30
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import get_db  # noqa: E402
from racing import bsp_files, store  # noqa: E402
from racing.live_features import horse_key  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    print(f"filled {bsp_files.fill_bet_sp(days=a.days)} bet(s)", flush=True)
    conn = get_db()
    store.ensure_tables(conn)
    rows = conn.execute(
        "SELECT r.date, b.horse, x.exchange_sp FROM rac_bets b JOIN rac_races r ON r.id = b.race_id "
        "LEFT JOIN rac_results x ON x.race_id = b.race_id AND x.horse_id = b.horse_id ORDER BY r.date").fetchall()
    conn.close()
    print(f"{len(rows)} tracked bet(s); today {date.today()}")
    names = {}
    for d, horse, sp in rows:
        d = str(d)[:10]
        if sp:
            print(f"  {d} {horse}: SP {sp}")
            continue
        if d not in names:
            names[d] = {}
            for region in ("uk", "ire"):
                text = bsp_files.fetch(region, "win", date.fromisoformat(d))
                print(f"  [{d} {region} file: {'%d rows' % text.count(chr(10)) if text else 'not available'}]")
                for r in bsp_files._rows_of(text):
                    names[d][horse_key(r.get("SELECTION_NAME"))] = r.get("BSP")
        hit = names[d].get(horse_key(horse))
        why = "today: file comes tomorrow" if d >= date.today().isoformat() else \
            (f"in file, BSP {hit!r}" if hit is not None else "not found in the file by name")
        print(f"  {d} {horse}: no SP ({why})")
    for f in bsp_files.failures[-5:]:
        print("  download:", f)


if __name__ == "__main__":
    main()
