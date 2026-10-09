#!/usr/bin/env python3
"""
The Stables: have today's finished Betfair races got results? Counts races that went off
since --since (UK time) and more than 20 minutes ago, and lists any without a result.

    venv/bin/python scripts/stables_results_check.py              # since 16:00 UK
    venv/bin/python scripts/stables_results_check.py --since 12:00
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import get_db  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="16:00")
    a = ap.parse_args()
    now = datetime.now(ZoneInfo("Europe/London"))
    upto = (now - timedelta(minutes=20)).strftime("%H:%M")
    c = get_db()
    rows = c.execute(
        "SELECT r.time, co.name, r.place_markets IS NOT NULL, "
        "EXISTS(SELECT 1 FROM rac_results x WHERE x.race_id = r.id AND x.finish_position = 1), "
        "(SELECT COUNT(*) FROM rac_runners ru WHERE ru.race_id = r.id AND ru.selection_id IS NOT NULL) "
        "FROM rac_races r LEFT JOIN rac_courses co ON co.id = r.course_id WHERE r.date = ? "
        "AND r.external_id LIKE 'bf:%' AND r.time BETWEEN ? AND ? ORDER BY r.time",
        (now.date().isoformat(), a.since, upto)).fetchall()
    c.close()
    done = sum(1 for r in rows if r[3])
    print(f"UK {now:%H:%M}: {len(rows)} races off between {a.since} and {upto}, {done} with results")
    for t, course, pm, res, sel in rows:
        if not res:
            print(f"  missing: {t} {course}  (saved runner ids: {sel}, place markets saved: {'yes' if pm else 'no'})")


if __name__ == "__main__":
    main()
