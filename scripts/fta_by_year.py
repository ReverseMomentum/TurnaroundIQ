#!/usr/bin/env python3
"""
Turnaround (FTA) rate by year and data source — spots data quirks.

    venv/bin/python scripts/fta_by_year.py

"FTA rate" = share of team-sides that went 2 goals up and failed to win.
Historically ~1.9-2.1% per year; a jump confined to one source points at the data.
"""
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models import fta_path_model as pm  # noqa: E402


def main():
    groups = defaultdict(lambda: [0, 0, 0])  # (year, source) -> [fta, went 2 up, sides]
    for m in pm.load_matches():
        year = date.fromordinal(m["day"]).year
        for side, (gf, ga) in ((1, (m["fh"], m["fa"])), (2, (m["fa"], m["fh"]))):
            s = m["sides"][side]
            g = groups[(year, m.get("source", "?"))]
            g[0] += int(bool(s["up2"]) and gf <= ga)
            g[1] += int(bool(s["up2"]))
            g[2] += 1
    print(f"{'year':<6}{'source':<22}{'sides':>8}{'2-up %':>9}{'FTA %':>8}{'fail|2up':>10}")
    for (year, src), (fta, up2, n) in sorted(groups.items()):
        print(f"{year:<6}{src:<22}{n:>8}{100 * up2 / n:>8.1f}%{100 * fta / n:>7.2f}%"
              f"{100 * fta / max(up2, 1):>9.1f}%")


if __name__ == "__main__":
    main()
