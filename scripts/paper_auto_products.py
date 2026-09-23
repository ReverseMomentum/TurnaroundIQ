"""
Paper-trade all three products from the same upcoming slate.

    python -u scripts/paper_auto_products.py --user dev_user --dry-run
    python -u scripts/paper_auto_products.py --user dev_user --products fta,early,chaos --limit 8
    python -u scripts/paper_auto_products.py --user dev_user --settle-only

During international breaks, widen the net:
    python -u scripts/paper_auto_products.py --user dev_user --min-fta 0.5 --min-hunter 20 --min-chaos 40 --limit 15
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
from models.opportunities_engine import rank_opportunities
from models.early_goal_hunter import rank_early_goal_matches
from models.chaos_index import rank_chaos_matches

try:
    from api.app import upcoming_match_pairs, latest_fixtures
except Exception:
    upcoming_match_pairs = None
    latest_fixtures = None


def _fta_pct(row) -> float:
    try:
        p = float(row.get("fta_pct") or 0)
    except (TypeError, ValueError):
        return 0.0
    if 0 < p <= 1.0:
        p *= 100.0
    return max(0.0, min(100.0, p))


def _already_open(user_id, product, home, away, team=None):
    for b in store.list_tracked(user_id, status="open", limit=300):
        if (b.get("product") or "fta") != product:
            continue
        if (b.get("home_team") or "").lower() != (home or "").lower():
            continue
        if (b.get("away_team") or "").lower() != (away or "").lower():
            continue
        if team and (b.get("team") or "").lower() != (team or "").lower():
            continue
        return True
    return False


def _open(user_id, payload, dry_run):
    if dry_run:
        return {"dry": True, **{k: payload.get(k) for k in (
            "product", "home_team", "away_team", "team", "fta_pct", "notes", "back_odds"
        )}}
    return store.create_tracked(user_id, payload)


def pick_fta(user_id, pairs, limit, min_fta, dry_run, settings):
    fixtures = []
    for p in pairs:
        base = {
            "match_id": p.get("match_id"),
            "kickoff": p.get("kickoff"),
            "league": p.get("league") or "",
            "home_team": p["home_team"],
            "away_team": p["away_team"],
            "bookmaker": "Paper-Auto",
            "back_odds": float(os.environ.get("DEFAULT_BACK_ODDS", "2.10")),
            "odds_estimated": True,
        }
        fixtures.append({**base, "team": p["home_team"], "is_home": True})
        fixtures.append({**base, "team": p["away_team"], "is_home": False})
    ranked = rank_opportunities(fixtures)
    ranked.sort(key=_fta_pct, reverse=True)
    out = []
    for row in ranked:
        pct = _fta_pct(row)
        if pct < min_fta:
            continue
        home, away, team = row.get("home_team"), row.get("away_team"), row.get("team")
        if _already_open(user_id, "fta", home, away, team):
            continue
        payload = {
            "product": "fta",
            "home_team": home,
            "away_team": away,
            "team": team,
            "is_home": row.get("is_home", True),
            "league": row.get("league") or "",
            "kickoff": row.get("kickoff"),
            "match_id": row.get("match_id"),
            "bookmaker": "Paper-Auto-FTA",
            "back_odds": row.get("back_odds") or 2.1,
            "stake": settings["default_stake"],
            "commission": settings["default_commission"],
            "fta_pct": round(pct, 4),
            "notes": f"fta auto {pct:.2f}%",
            "paper": True,
        }
        out.append(_open(user_id, payload, dry_run))
        if len(out) >= limit:
            break
    return out


def pick_early(user_id, pairs, limit, min_hunter, dry_run, settings):
    ranked = rank_early_goal_matches(pairs)
    out = []
    for row in ranked:
        score = float(row.get("hunter_score") or 0)
        if score < min_hunter:
            continue
        home, away = row.get("home_team"), row.get("away_team")
        if _already_open(user_id, "early_goal", home, away):
            continue
        # Selection: match-level early goal (1H goal market style)
        payload = {
            "product": "early_goal",
            "home_team": home,
            "away_team": away,
            "team": home,  # match-level; settle on either early flag
            "is_home": True,
            "league": row.get("league") or "",
            "kickoff": row.get("kickoff"),
            "match_id": row.get("match_id"),
            "bookmaker": "Paper-Auto-Early",
            "back_odds": 1.9,
            "stake": settings["default_stake"],
            "commission": settings["default_commission"],
            "fta_pct": score,  # reuse column as score display
            "notes": f"early hunter_score={score} p_1h={row.get('p_first_half_goal')}",
            "paper": True,
        }
        out.append(_open(user_id, payload, dry_run))
        if len(out) >= limit:
            break
    return out


def pick_chaos(user_id, pairs, limit, min_chaos, dry_run, settings):
    ranked = rank_chaos_matches(pairs)
    out = []
    for row in ranked:
        score = float(row.get("chaos_index") or 0)
        if score < min_chaos:
            continue
        home, away = row.get("home_team"), row.get("away_team")
        if _already_open(user_id, "chaos", home, away):
            continue
        comps = row.get("components") or {}
        payload = {
            "product": "chaos",
            "home_team": home,
            "away_team": away,
            "team": home,
            "is_home": True,
            "league": row.get("league") or "",
            "kickoff": row.get("kickoff"),
            "match_id": row.get("match_id"),
            "bookmaker": "Paper-Auto-Chaos",
            "back_odds": 2.0,
            "stake": settings["default_stake"],
            "commission": settings["default_commission"],
            "fta_pct": score,
            "notes": (
                f"chaos={score} btts={comps.get('btts')} o25={comps.get('o2_5')} "
                f"early={comps.get('early_goal')} inst={comps.get('instability')}"
            ),
            "paper": True,
        }
        out.append(_open(user_id, payload, dry_run))
        if len(out) >= limit:
            break
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", default=os.environ.get("PAPER_USER", "dev_user"))
    p.add_argument("--products", default="fta,early,chaos",
                   help="Comma list: fta,early,chaos")
    p.add_argument("--limit", type=int, default=8, help="Max opens per product")
    p.add_argument("--min-fta", type=float, default=1.0)
    p.add_argument("--min-hunter", type=float, default=25.0)
    p.add_argument("--min-chaos", type=float, default=45.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--settle-only", action="store_true")
    args = p.parse_args()

    if args.settle_only:
        n = store.auto_settle_from_results(args.user)
        print(json.dumps({
            "settled": n,
            "summary": store.summary(args.user),
            "by_product": store.summary_by_product(args.user),
        }, indent=2))
        return

    if upcoming_match_pairs is None:
        raise SystemExit("Could not import upcoming_match_pairs")

    pairs = upcoming_match_pairs(80)
    settings = store.get_paper_settings(args.user)
    products = [x.strip().lower() for x in args.products.split(",") if x.strip()]

    result = {
        "dry_run": args.dry_run,
        "pairs": len(pairs),
        "products": products,
        "opened": {},
    }

    if "fta" in products:
        result["opened"]["fta"] = pick_fta(
            args.user, pairs, args.limit, args.min_fta, args.dry_run, settings
        )
    if "early" in products or "early_goal" in products:
        result["opened"]["early_goal"] = pick_early(
            args.user, pairs, args.limit, args.min_hunter, args.dry_run, settings
        )
    if "chaos" in products:
        result["opened"]["chaos"] = pick_chaos(
            args.user, pairs, args.limit, args.min_chaos, args.dry_run, settings
        )

    result["counts"] = {k: len(v) for k, v in result["opened"].items()}
    result["summary"] = store.summary(args.user)
    result["by_product"] = store.summary_by_product(args.user)
    # Compact dry-run print
    if args.dry_run:
        compact = {}
        for prod, items in result["opened"].items():
            compact[prod] = [
                {
                    "match": f"{i.get('home_team')} vs {i.get('away_team')}",
                    "team": i.get("team"),
                    "score": i.get("fta_pct"),
                    "notes": i.get("notes"),
                }
                for i in items
            ]
        result["opened"] = compact
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
