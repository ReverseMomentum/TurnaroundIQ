#!/usr/bin/env python3
"""
The Stables: price every race on a date and store P1..P9, predictions and
opportunities (rac_position_probabilities / rac_model_predictions /
rac_opportunities), then print the opportunities.

    venv/bin/python scripts/stables_run.py              # today (UTC)
    venv/bin/python scripts/stables_run.py 2026-10-02
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from racing import store  # noqa: E402
from racing.engine import price_race  # noqa: E402


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    cal = store.latest_calibration()
    races = store.races_on(date)
    print(f"{date}: {len(races)} races, discounts {'fitted' if cal.get('fitted') else 'prior'}")
    for race in races:
        priced = price_race(race, cal)
        store.save_priced(priced)
        for o in priced["opportunities"]:
            print(f"  {race.get('time') or '':<6}{(race.get('course') or '')[:14]:<15}{o['horse'][:22]:<23}"
                  f"{o['bookmaker'][:12]:<13}{o['places_paid']} pl  model {100 * o['model_probability']:5.1f}%"
                  f"  market {100 * o['market_probability']:5.1f}%  EW EV {100 * o['each_way_ev']:+5.1f}%"
                  f"  conf {o['confidence']:>3}  {o['grade']}")


if __name__ == "__main__":
    main()
