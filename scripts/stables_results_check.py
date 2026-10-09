#!/usr/bin/env python3
"""
The Stables: have today's finished Betfair races got results? Counts races that went off
since --since (UK time) and more than 20 minutes ago, and lists any without a result.

    venv/bin/python scripts/stables_results_check.py              # since 16:00 UK
    venv/bin/python scripts/stables_results_check.py --since 12:00
    scripts/cron_job.sh rcheck python -u scripts/stables_results_check.py --betfair   # ask Betfair about the missing ones
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import get_db  # noqa: E402
from racing import store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="16:00")
    ap.add_argument("--betfair", action="store_true", help="ask Betfair what it says about each missing race")
    a = ap.parse_args()
    now = datetime.now(ZoneInfo("Europe/London"))
    upto = (now - timedelta(minutes=20)).strftime("%H:%M")
    c = get_db()
    store.ensure_tables(c)
    rows = c.execute(
        "SELECT r.time, co.name, r.place_markets IS NOT NULL AND r.place_markets != '{}', "
        "EXISTS(SELECT 1 FROM rac_results x WHERE x.race_id = r.id AND x.finish_position = 1), "
        "(SELECT COUNT(*) FROM rac_runners ru WHERE ru.race_id = r.id AND ru.selection_id IS NOT NULL) "
        "FROM rac_races r LEFT JOIN rac_courses co ON co.id = r.course_id WHERE r.date = ? "
        "AND r.external_id LIKE 'bf:%' AND r.time BETWEEN ? AND ? ORDER BY r.time",
        (now.date().isoformat(), a.since, upto)).fetchall()
    allpm = c.execute("SELECT COUNT(*), SUM(place_markets IS NOT NULL AND place_markets != '{}') FROM rac_races "
                      "WHERE date = ? AND external_id LIKE 'bf:%'", (now.date().isoformat(),)).fetchone()
    ids = {r[0]: r[1] for r in c.execute(
        "SELECT r.time || ' ' || co.name, r.external_id FROM rac_races r LEFT JOIN rac_courses co ON co.id = r.course_id "
        "WHERE r.date = ?", (now.date().isoformat(),))}
    c.close()
    print(f"today: {allpm[0]} Betfair races, {allpm[1] or 0} with place markets saved")
    done = sum(1 for r in rows if r[3])
    print(f"UK {now:%H:%M}: {len(rows)} races off between {a.since} and {upto}, {done} with results")
    for t, course, pm, res, sel in rows:
        if not res:
            print(f"  missing: {t} {course}  (saved runner ids: {sel}, place markets saved: {'yes' if pm else 'no'})")
            if a.betfair:
                ask(ids.get(f"{t} {course}"))


def ask(ext):
    """What Betfair's API returns now for the race's WIN market."""
    from collectors.betfair import BetfairError, Client

    if not ext or not ext.startswith("bf:"):
        return
    try:
        cl = Client()
        books = cl.call("listMarketBook", {"marketIds": [ext[3:]], "priceProjection": {"priceData": ["SP_TRADED"]}})
        cat = cl.call("listMarketCatalogue", {"filter": {"marketIds": [ext[3:]]}, "maxResults": 1,
                                              "marketProjection": ["EVENT"]})
    except BetfairError as e:
        print(f"    Betfair error: {e}")
        return
    if not books:
        print(f"    market {ext[3:]}: Betfair returned no book")
        return
    b = books[0]
    st = [r.get("status") for r in b.get("runners") or []]
    sp = sum(1 for r in b.get("runners") or [] if (r.get("sp") or {}).get("actualSP"))
    print(f"    market {ext[3:]}: status {b.get('status')}, runners {len(st)}, winners {st.count('WINNER')}, "
          f"with SP {sp}, still in catalogue: {'yes' if cat else 'no'}")


if __name__ == "__main__":
    main()
