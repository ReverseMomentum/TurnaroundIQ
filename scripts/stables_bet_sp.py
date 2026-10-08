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
            names[d] = bsp_files.bsp_by_horse(date.fromisoformat(d))
            print(f"  [{d}: {len(names[d])} runners with a BSP in the files]")
        hit = names[d].get(horse_key(horse))
        if hit is None and names[d]:
            import difflib

            close = difflib.get_close_matches(horse_key(horse), list(names[d]), n=2, cutoff=0.6)
            print(f"    looking for {horse_key(horse)!r}; closest in file: {close}; "
                  f"sample names: {list(names[d])[:3]}")
        why = "Betfair's file for that day isn't out yet (usually the next morning)" if not names[d] else \
            (f"in file, BSP {hit!r}" if hit is not None else "not found in the file by name")
        print(f"  {d} {horse}: no SP ({why})")
    for f in bsp_files.failures[-5:]:
        print("  download:", f)


if __name__ == "__main__":
    main()
