#!/usr/bin/env python3
"""
Scout leagues we don't cover yet (e.g. youth) before adding them. Read-only.

    venv/bin/python scripts/league_scout.py search                 # youth leagues api-sports has
    venv/bin/python scripts/league_scout.py search "Primavera"     # your own search words
    venv/bin/python scripts/league_scout.py probe 702 703          # sample their last full season
    venv/bin/python scripts/league_scout.py probe 702 --season 2024 --sample 300

`probe` costs 1 call per league for the season list (cached a week) + 1 for the
fixtures + 1 per 20 matches sampled (default 200 -> ~12 calls per league).
It reports the same columns as scripts/league_report.py, next to our average.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collectors import apisports as af  # noqa: E402
from collectors import backfill_apisports as bf  # noqa: E402
from models import fta_path_model as pm  # noqa: E402
from scripts.league_report import league_stats, print_table  # noqa: E402
from team_normalizer import normalize_team  # noqa: E402

YOUTH_WORDS = ["U21", "U23", "U19", "U20", "U18", "Youth", "Primavera", "Reserve",
               "Premier League 2", "Development"]


def search(words):
    seen = set()
    print(f"{'id':>6}  {'league':<34}{'country':<16}{'latest':>7}  events")
    for w in words:
        payload = af.api_get("/leagues", {"search": w})
        for item in payload.get("response") or []:
            lg, country = item.get("league") or {}, item.get("country") or {}
            if lg.get("id") in seen:
                continue
            seen.add(lg.get("id"))
            seasons = sorted(item.get("seasons") or [], key=lambda s: s.get("year") or 0)
            last = seasons[-1] if seasons else {}
            ev = ((last.get("coverage") or {}).get("fixtures") or {}).get("events")
            print(f"{lg.get('id'):>6}  {(lg.get('name') or '')[:33]:<34}{(country.get('name') or '')[:15]:<16}"
                  f"{last.get('year') or '':>7}  {'yes' if ev else 'NO'}")
    print("\nOnly leagues with events = yes can be scored (we need goal minutes). Probe the ones you like.")


def probe(league_id, season=None, sample=200):
    if season is None:
        seasons = bf.league_seasons(league_id)
        done = [s for s in seasons if not s["current"] and s["events_covered"]]
        if not done:
            print(f"league {league_id}: no completed season with goal events")
            return None, None
        season = done[0]["year"]
    fixtures = bf.finished_fixtures(league_id, season)
    if not fixtures:
        print(f"league {league_id} {season}: no finished fixtures")
        return None, None
    name = ((fixtures[0].get("league") or {}).get("name") or str(league_id))
    fixtures = fixtures[-sample:]
    matches, rejected = [], 0
    for i in range(0, len(fixtures), bf.BATCH):
        batch = fixtures[i:i + bf.BATCH]
        events = bf.fixtures_with_events([f["fixture"]["id"] for f in batch])
        for f in batch:
            home, away = f["teams"]["home"], f["teams"]["away"]
            fh, fa = bf.official_score(f)
            if fh is None:
                rejected += 1
                continue
            goals, _rule, _reason = bf.resolve_goals(
                events.get(f["fixture"]["id"]) or [], home.get("id"), away.get("id"),
                normalize_team(home.get("name") or ""), normalize_team(away.get("name") or ""), fh, fa)
            if goals is None:
                rejected += 1
                continue
            timeline = [(minute, side) for minute, side, *_ in goals]
            matches.append({"league": f"{name} ({season})", "fh": fh, "fa": fa,
                            "sides": pm._side_outcomes(timeline, fh, fa)})
    print(f"league {league_id} {name} {season}: {len(matches)} matches usable, {rejected} rejected "
          f"(goal events didn't match the score)")
    return f"{name} ({season})", matches


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("words", nargs="*")
    p = sub.add_parser("probe")
    p.add_argument("league_ids", nargs="+", type=int)
    p.add_argument("--season", type=int)
    p.add_argument("--sample", type=int, default=200)
    args = ap.parse_args()
    af.require_key()
    if args.cmd == "search":
        search(args.words or YOUTH_WORDS)
        return
    all_matches = []
    for lid in args.league_ids:
        try:
            _, ms = probe(lid, args.season, args.sample)
        except (af.QuotaExhausted, af.AuthError, af.NetworkError) as exc:
            print(f"stopped: {exc}")
            break
        all_matches += ms or []
    if not all_matches:
        return
    ours = league_stats([dict(m, league="OUR LEAGUES (all)") for m in pm.load_matches()])
    scouted = league_stats(all_matches)
    print()
    print_table({**scouted, **ours}, "Scouted leagues vs our current leagues combined:")
    print("Small samples are noisy: with ~200 matches the FTA ± is about ±0.9 points.")


if __name__ == "__main__":
    main()
