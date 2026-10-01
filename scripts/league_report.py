#!/usr/bin/env python3
"""
How turnaround-prone each league is, from our own match data.

    venv/bin/python scripts/league_report.py            # all seasons
    venv/bin/python scripts/league_report.py --since 2023

Per league (per team-side unless noted):
  goals   goals per match
  early   % of matches with a goal in the first 30 minutes
  2-up    % of team-sides that went 2 goals up
  fail    % of those 2-goal leads that did NOT end in a win
  FTA     % of team-sides that went 2 up AND failed to win (what the app ranks)
  vs avg  FTA relative to the all-league average (1.20x = 20% more turnarounds)
  ±       rough 95% margin on FTA from sample size
"""
import argparse
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models import fta_path_model as pm  # noqa: E402


def league_stats(matches):
    """{league: dict} from load_matches()-style dicts."""
    acc = defaultdict(lambda: defaultdict(float))
    for m in matches:
        a = acc[m["league"] or "?"]
        a["matches"] += 1
        a["goals"] += m["fh"] + m["fa"]
        a["early"] += int(m["sides"][1]["early_for"] > 0 or m["sides"][2]["early_for"] > 0)
        for side, (gf, ga) in ((1, (m["fh"], m["fa"])), (2, (m["fa"], m["fh"]))):
            s = m["sides"][side]
            a["sides"] += 1
            if s["up2"]:
                a["up2"] += 1
                if gf <= ga:
                    a["fta"] += 1
    out = {}
    for lg, a in acc.items():
        n, up2 = a["sides"], a["up2"]
        fta = a["fta"] / n if n else 0.0
        out[lg] = {
            "matches": int(a["matches"]),
            "goals": a["goals"] / a["matches"],
            "early": 100 * a["early"] / a["matches"],
            "up2": 100 * up2 / n if n else 0.0,
            "fail": 100 * a["fta"] / up2 if up2 else 0.0,
            "fta": 100 * fta,
            "margin": 100 * 1.96 * math.sqrt(max(fta * (1 - fta), 1e-9) / max(n, 1)),
        }
    return out


def print_table(stats, title, min_matches=0):
    rows = [(lg, s) for lg, s in stats.items() if s["matches"] >= min_matches]
    if not rows:
        print("no leagues with enough matches")
        return
    total_sides = sum(2 * s["matches"] for _, s in rows)
    avg = sum(s["fta"] * 2 * s["matches"] for _, s in rows) / total_sides
    print(title)
    print(f"{'league':<26}{'matches':>8}{'goals':>7}{'early':>7}{'2-up':>7}{'fail':>7}{'FTA':>7}{'±':>6}{'vs avg':>8}")
    for lg, s in sorted(rows, key=lambda r: -r[1]["fta"]):
        print(f"{lg[:25]:<26}{s['matches']:>8}{s['goals']:>7.2f}{s['early']:>6.0f}%{s['up2']:>6.1f}%"
              f"{s['fail']:>6.1f}%{s['fta']:>6.2f}%{s['margin']:>5.2f}{s['fta'] / avg:>7.2f}x")
    print(f"\nall leagues: FTA {avg:.2f}% per team-side. Leagues whose FTA ± overlaps the average "
          "aren't reliably different yet.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, help="only matches from this year on")
    ap.add_argument("--min-matches", type=int, default=150)
    args = ap.parse_args()
    matches = pm.load_matches()
    if args.since:
        matches = [m for m in matches if date.fromordinal(m["day"]).year >= args.since]
    print_table(league_stats(matches), f"{len(matches)} matches"
                + (f" since {args.since}" if args.since else ""), args.min_matches)


if __name__ == "__main__":
    main()
