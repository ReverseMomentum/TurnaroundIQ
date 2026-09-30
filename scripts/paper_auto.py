"""
Automatically open paper trades from ranked opportunities, bucketed by FTA%.

    # Dry run — show what would be taken
    python -u scripts/paper_auto.py --user dev_user --dry-run

    # Take top 10 by FTA%, min 1.5% (full event)
    python -u scripts/paper_auto.py --user dev_user --limit 10 --min-fta 1.5

    # Then auto-settle finished ones
    python -u scripts/paper_auto.py --user dev_user --settle-only

Cron-friendly: run after results_collector + once before kickoffs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import tracked as store
from models.opportunities_engine import fta_band, rank_opportunities

try:
    from api.app import latest_fixtures
except Exception:
    latest_fixtures = None


def _fta_value(row) -> float:
    """fta_pct is percent (full event, e.g. 2.4). Clamp to 0–100."""
    try:
        p = float(row.get("fta_pct") or 0)
    except (TypeError, ValueError):
        return 0.0
    return min(max(p, 0.0), 100.0)


def _band(pct: float) -> str:
    return fta_band(pct)


def _already_open(user_id: str, home: str, away: str, team: str) -> bool:
    for b in store.list_tracked(user_id, status="open", limit=200):
        if (
            (b.get("home_team") or "").lower() == (home or "").lower()
            and (b.get("away_team") or "").lower() == (away or "").lower()
            and (b.get("team") or "").lower() == (team or "").lower()
        ):
            return True
    return False


def fetch_ranked(limit: int = 40):
    if latest_fixtures is None:
        raise RuntimeError("Could not import latest_fixtures from api.app")
    fixtures = latest_fixtures(limit=max(limit, 20))
    ranked = rank_opportunities(fixtures)
    ranked.sort(key=_fta_value, reverse=True)
    return ranked


def run_auto(
    user_id: str,
    limit: int = 10,
    min_fta: float = 3.0,
    dry_run: bool = False,
):
    settings = store.get_paper_settings(user_id)
    ranked = fetch_ranked(limit=max(limit * 3, 40))
    selected = []
    for row in ranked:
        pct = _fta_value(row)
        if pct < min_fta:
            continue
        home = row.get("home_team") or ""
        away = row.get("away_team") or ""
        team = row.get("team") or home
        if not home or not away:
            continue
        if _already_open(user_id, home, away, team):
            continue
        selected.append(row)
        if len(selected) >= limit:
            break

    buckets: dict[str, list] = {}
    for row in selected:
        pct = _fta_value(row)
        buckets.setdefault(_band(pct), []).append(
            {
                "match": row.get("match") or f"{row.get('home_team')} vs {row.get('away_team')}",
                "team": row.get("team"),
                "fta_pct": round(pct, 2),
                "band": _band(pct),
                "back_odds": row.get("back_odds"),
                "league": row.get("league"),
            }
        )

    opened = []
    if not dry_run:
        for row in selected:
            pct = _fta_value(row)
            payload = {
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "team": row.get("team"),
                "is_home": row.get("is_home", True),
                "league": row.get("league") or "",
                "kickoff": row.get("kickoff"),
                "match_id": row.get("match_id"),
                "bookmaker": row.get("bookmaker") or "Paper-Auto",
                "back_odds": row.get("back_odds"),
                "lay_odds": row.get("lay_odds"),
                "stake": settings["default_stake"],
                "commission": settings["default_commission"],
                "fta_pct": round(pct, 4),  # store as percent 0–100
                "notes": f"auto band={_band(pct)}",
                "paper": True,
                "lay_stake": row.get("lay_stake"),
                "liability": row.get("liability"),
            }
            bet = store.create_tracked(user_id, payload)
            opened.append(bet)

    return {
        "dry_run": dry_run,
        "min_fta": min_fta,
        "limit": limit,
        "candidates_scanned": len(ranked),
        "selected": len(selected),
        "opened": len(opened),
        "by_band": {k: len(v) for k, v in buckets.items()},
        "buckets": buckets,
        "summary": store.summary(user_id),
        "band_performance": store.summary_by_fta_band(user_id),
    }


def main():
    p = argparse.ArgumentParser(description="Auto paper trade by FTA%")
    p.add_argument("--user", default=os.environ.get("PAPER_USER", "dev_user"))
    p.add_argument("--limit", type=int, default=10)
    p.add_argument(
        "--min-fta",
        type=float,
        default=1.5,
        help="Minimum full-event FTA% to take (e.g. 1.5 = 1.5%)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--settle-only",
        action="store_true",
        help="Only auto-settle from match_results",
    )
    args = p.parse_args()

    if args.settle_only:
        n = store.auto_settle_from_results(args.user)
        out = {
            "settled": n,
            "summary": store.summary(args.user),
            "band_performance": store.summary_by_fta_band(args.user),
        }
        print(json.dumps(out, indent=2))
        return

    out = run_auto(
        args.user,
        limit=args.limit,
        min_fta=args.min_fta,
        dry_run=args.dry_run,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
