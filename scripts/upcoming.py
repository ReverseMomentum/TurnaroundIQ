#!/usr/bin/env python3
"""
What the app sees: upcoming fixtures in supported leagues, their FTA%, and
whether each would show on Picks (inside the 24h window and above the floor).

    venv/bin/python scripts/upcoming.py           # next 48 hours
    venv/bin/python scripts/upcoming.py 72
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api import app  # noqa: E402
from models.opportunities_engine import rank_opportunities  # noqa: E402

FLOOR = 1.8   # keep in step with MIN_FTA in mobile/src/lib/api.js
WINDOW = 24


def main():
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    fixtures = app.fixtures_from_upcoming(limit=400, hours=hours)
    print(f"fixture source: {app.fixture_meta()}")
    if not fixtures:
        print(f"No fixtures in supported leagues in the next {hours}h.")
        return
    now = datetime.now(timezone.utc)
    print(f"{'kick-off (UK)':<17}{'in 24h':<8}{'FTA %':>6}  {'shows?':<7} league / match / 2-up team")
    for o in sorted(rank_opportunities(fixtures), key=lambda o: (o.get("kickoff") or "", -(o.get("fta_pct") or 0))):
        ko = datetime.fromisoformat(str(o["kickoff"]).replace("Z", "+00:00"))
        uk = ko.astimezone().strftime("%a %d %H:%M")
        inside = (ko - now).total_seconds() <= WINDOW * 3600
        shows = inside and (o.get("fta_pct") or 0) >= FLOOR
        print(f"{uk:<17}{'yes' if inside else 'no':<8}{o.get('fta_pct', 0):>6.2f}  {'YES' if shows else '-':<7} "
              f"{o.get('league')} / {o.get('match')} / {o.get('team')}")


if __name__ == "__main__":
    main()
