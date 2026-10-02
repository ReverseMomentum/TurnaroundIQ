#!/usr/bin/env python3
"""
Sweep every league api-sports covers for turnaround promise. Read-only for the app.

    venv/bin/python -u scripts/league_sweep.py sweep              # resumable; ~1 call per league
    venv/bin/python -u scripts/league_sweep.py sweep --max-calls 300
    venv/bin/python -u scripts/league_sweep.py top                # ranked table from what's swept
    venv/bin/python -u scripts/league_sweep.py top --all          # include women's / cup-like / tiny

Stage 1 (this script) is cheap: one /fixtures call per league for its last
completed season, using only half-time and full-time scores:
  goals   goals per match
  2up+    % of team-sides 2+ goals ahead at half-time or full-time (a floor on
          the true 2-up rate, which also counts leads that later shrank)
  HTfail  % of team-sides 2+ up at half-time that then failed to win (a slice
          of FTA; rare, so noisy on small samples)
Our current leagues are swept too, as the benchmark ("ours" column).

Stage 2: confirm the best few with goal timelines, the real FTA:
    venv/bin/python -u scripts/league_scout.py probe <id> <id> --sample 300

Only leagues whose latest completed season has goal events AND odds coverage
are swept (no events = can't be modelled; no odds = no prices in the app).
Results are saved in data/league_sweep.csv, so a run that stops at the call
limit or the daily quota carries on where it left off next time.
"""
import argparse
import csv
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collectors import apisports as af  # noqa: E402
from collectors import backfill_apisports as bf  # noqa: E402
from constants import SUPPORTED_LEAGUE_IDS  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
CATALOG = DATA / "league_catalog.json"
OUT = DATA / "league_sweep.csv"
FIELDS = ["id", "league", "country", "season", "ours", "kind", "matches", "goals",
          "up2", "htfail", "at"]
CATALOG_DAYS = 7

WOMEN = re.compile(r"\b(women|womens|women's|feminin|femenin|frauen|w-league|wsl|nwsl|damallsvenskan|ladies)\b", re.I)
YOUTH = re.compile(r"\b(u\d{2}|youth|primavera|reserve|reserves|development|junior|juniores|sub-\d{2}|II)\b|premier league 2", re.I)


def kind_of(name):
    if WOMEN.search(name or ""):
        return "women"
    if YOUTH.search(name or ""):
        return "youth"
    return "senior"


def load_catalog(refresh=False):
    """Every league api-sports lists, cached for a week (1 call)."""
    if CATALOG.exists() and not refresh:
        try:
            cached = json.loads(CATALOG.read_text())
            age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["at"])
            if age.days < CATALOG_DAYS:
                return cached["leagues"]
        except (KeyError, ValueError):
            pass
    payload = af.api_get("/leagues", {})
    leagues = payload.get("response") or []
    DATA.mkdir(exist_ok=True)
    CATALOG.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "leagues": leagues}))
    return leagues


def sweep_season(item):
    """Latest completed season with goal events and odds, or None."""
    seasons = sorted(item.get("seasons") or [], key=lambda s: s.get("year") or 0, reverse=True)
    for s in seasons:
        if s.get("current"):
            continue
        cov = s.get("coverage") or {}
        if (cov.get("fixtures") or {}).get("events") and cov.get("odds"):
            return s.get("year")
    return None


def candidates(catalog):
    out = []
    for item in catalog:
        lg, country = item.get("league") or {}, item.get("country") or {}
        if lg.get("type") != "League":
            continue
        season = sweep_season(item)
        if not season:
            continue
        name = lg.get("name") or ""
        out.append({"id": lg.get("id"), "league": name, "country": country.get("name") or "",
                    "season": season, "ours": lg.get("id") in SUPPORTED_LEAGUE_IDS,
                    "kind": kind_of(name)})
    # our leagues first (the benchmark), then the rest
    return sorted(out, key=lambda c: (not c["ours"], c["country"], c["league"]))


def score_fixtures(fixtures):
    """Stage-1 numbers from half-time / full-time scores only."""
    matches = goals = sides = up2 = ht2 = htfail = 0
    for f in fixtures:
        ft_h, ft_a = bf.official_score(f)
        ht = ((f.get("score") or {}).get("halftime") or {})
        ht_h, ht_a = ht.get("home"), ht.get("away")
        if ft_h is None or ht_h is None or ht_a is None:
            continue
        matches += 1
        goals += ft_h + ft_a
        for ht_m, ft_m in ((ht_h - ht_a, ft_h - ft_a), (ht_a - ht_h, ft_a - ft_h)):
            sides += 1
            if ht_m >= 2 or ft_m >= 2:
                up2 += 1
            if ht_m >= 2:
                ht2 += 1
                if ft_m <= 0:
                    htfail += 1
    if not matches:
        return None
    return {"matches": matches, "goals": goals / matches,
            "up2": 100 * up2 / sides, "htfail": 100 * htfail / sides}


def load_done():
    if not OUT.exists():
        return {}
    with OUT.open() as fh:
        return {int(r["id"]): r for r in csv.DictReader(fh)}


def append_row(row):
    new = not OUT.exists()
    with OUT.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def sweep(max_calls, refresh_catalog=False):
    catalog = load_catalog(refresh_catalog)
    cands = candidates(catalog)
    done = load_done()
    todo = [c for c in cands if c["id"] not in done]
    print(f"leagues listed: {len(catalog)}; sweepable (league, events + odds): {len(cands)}; "
          f"already swept: {len(cands) - len(todo)}; to do: {len(todo)}")
    used = 0
    for c in todo:
        if used >= max_calls:
            print(f"stopped at the call limit ({max_calls}); run again to continue")
            break
        try:
            fixtures = bf.finished_fixtures(c["id"], c["season"])
        except af.QuotaExhausted as exc:
            print(f"stopped: {exc}; run again tomorrow to continue")
            break
        used += 1
        s = score_fixtures(fixtures) or {"matches": 0, "goals": 0, "up2": 0, "htfail": 0}
        append_row({**c, "ours": int(c["ours"]), "matches": s["matches"],
                    "goals": f"{s['goals']:.2f}", "up2": f"{s['up2']:.1f}",
                    "htfail": f"{s['htfail']:.2f}", "at": datetime.now(timezone.utc).isoformat()})
        if used % 25 == 0:
            print(f"  {used} calls, last: {c['league']} ({c['country']})")
    left = len([c for c in cands if c["id"] not in load_done()])
    print(f"done this run: {used} calls; leagues still to sweep: {left}")
    if not left:
        print("all swept: venv/bin/python -u scripts/league_sweep.py top")


def ranked(rows, min_matches=150, show_all=False):
    out = []
    for r in rows:
        m = int(r["matches"] or 0)
        if m < min_matches or (not show_all and r["kind"] == "women"):
            continue
        out.append({**r, "matches": m, "goals": float(r["goals"]), "up2": float(r["up2"]),
                    "htfail": float(r["htfail"]), "ours": r["ours"] in ("1", "True", True)})
    return sorted(out, key=lambda r: r["up2"], reverse=True)


def top(n=30, min_matches=150, show_all=False):
    rows = ranked(list(load_done().values()), min_matches, show_all)
    if not rows:
        print("nothing swept yet: venv/bin/python -u scripts/league_sweep.py sweep")
        return
    ours = [r for r in rows if r["ours"]]
    if ours:
        base_up2 = sum(r["up2"] * r["matches"] for r in ours) / sum(r["matches"] for r in ours)
        base_g = sum(r["goals"] * r["matches"] for r in ours) / sum(r["matches"] for r in ours)
        base_ht = sum(r["htfail"] * r["matches"] for r in ours) / sum(r["matches"] for r in ours)
        print(f"our leagues (benchmark): goals {base_g:.2f}  2up+ {base_up2:.1f}%  HTfail {base_ht:.2f}%")
    else:
        base_up2 = None
    print(f"\n{'id':>5}  {'league':<30}{'country':<13}{'yr':>5}{'kind':>7}{'n':>5}"
          f"{'goals':>6}{'2up+':>7}{'HTfail':>7}  note")
    shown = 0
    for r in rows:
        if r["ours"]:
            continue
        note = ""
        if base_up2:
            note = f"{r['up2'] / base_up2:.2f}x ours"
        # rough 95% margin on the 2up+ rate (team-sides = 2 per match)
        moe = 100 * 1.96 * math.sqrt(max(r["up2"] / 100 * (1 - r["up2"] / 100), 1e-9) / (2 * r["matches"]))
        print(f"{r['id']:>5}  {r['league'][:29]:<30}{r['country'][:12]:<13}{r['season']:>5}{r['kind']:>7}"
              f"{r['matches']:>5}{r['goals']:>6.2f}{r['up2']:>6.1f}%{r['htfail']:>6.2f}%  {note} ±{moe:.1f}")
        shown += 1
        if shown >= n:
            break
    print("\nRanked by 2up+ (how often games reach a 2-goal lead), the main driver of FTA.")
    print("Confirm the best with real goal timelines before adding any:")
    best = [str(r["id"]) for r in rows if not r["ours"]][:6]
    print(f"  venv/bin/python -u scripts/league_scout.py probe {' '.join(best)} --sample 300")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--max-calls", type=int, default=400)
    s.add_argument("--refresh-catalog", action="store_true")
    t = sub.add_parser("top")
    t.add_argument("--n", type=int, default=30)
    t.add_argument("--min-matches", type=int, default=150)
    t.add_argument("--all", action="store_true", help="include women's leagues")
    args = ap.parse_args()
    if args.cmd == "sweep":
        af.require_key()
        sweep(args.max_calls, args.refresh_catalog)
    else:
        top(args.n, args.min_matches, args.all)


if __name__ == "__main__":
    main()
