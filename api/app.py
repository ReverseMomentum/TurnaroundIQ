"""
Public API for the mobile app.

Segments:
  GET /opportunities     — 2UP / FTA (Pro)
  GET /features/early-goal — Early Goal Hunter (Pro)
  GET /features/chaos      — Chaos Index (Pro)
"""

from datetime import datetime, timezone
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from billing.revenuecat import (
    apply_webhook,
    get_prefs,
    get_subscriber_row,
    is_entitled,
    save_prefs,
    webhook_auth_ok,
    ensure_tables,
)
from database import get_db, create_tables
from models.opportunities_engine import rank_opportunities
from models.early_goal_hunter import rank_early_goal_matches
from models.chaos_index import rank_chaos_matches

CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
]

app = FastAPI(title="TurnaroundIQ", version="0.3")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PrefsPatch(BaseModel):
    default_stake: Optional[float] = None
    default_commission: Optional[float] = None
    risk_warning_pct: Optional[float] = None
    notify_opportunity: Optional[bool] = None
    notify_fixture_starting: Optional[bool] = None
    notify_live_trigger: Optional[bool] = None
    notify_exchange_entry: Optional[bool] = None


@app.on_event("startup")
def startup():
    create_tables()
    ensure_tables()


def user_from_auth(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(401, "Missing Authorization")
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return token


def require_pro(authorization: str | None) -> str:
    user_id = user_from_auth(authorization)
    if not is_entitled(user_id):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": "Pro subscription required",
            },
        )
    return user_id


def latest_fixtures(limit=40):
    """Odds rows for 2UP engine (per selection)."""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT match_id, kickoff, league, home_team, away_team,
                   selection, bookmaker, back_odds, lay_odds
            FROM odds_history
            WHERE id IN (
                SELECT MAX(id) FROM odds_history GROUP BY match_id, selection
            )
            ORDER BY kickoff DESC
            LIMIT ?
            """,
            (limit * 2,),
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    fixtures = []
    for row in rows:
        match_id, kickoff, league, home, away, selection, book, back, lay = row
        if back is None:
            continue
        fixtures.append({
            "match_id": match_id,
            "match": f"{home} vs {away}",
            "kickoff": kickoff,
            "league": league,
            "home_team": home,
            "away_team": away,
            "team": selection,
            "is_home": selection == home,
            "bookmaker": book,
            "back_odds": back,
            "lay_odds": lay,
        })
    return fixtures[:limit]


def latest_match_pairs(limit=40):
    """Unique home/away pairs for Early Goal + Chaos segments."""
    conn = get_db()
    pairs = []
    try:
        rows = conn.execute(
            """
            SELECT match_id, kickoff, league, home_team, away_team
            FROM odds_history
            WHERE home_team IS NOT NULL AND away_team IS NOT NULL
            GROUP BY home_team, away_team, IFNULL(kickoff, ''), IFNULL(league, '')
            ORDER BY MAX(id) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            pairs.append({
                "match_id": row[0],
                "kickoff": row[1],
                "league": row[2],
                "home_team": row[3],
                "away_team": row[4],
            })
    except Exception:
        pass

    if len(pairs) < 5:
        try:
            rows = conn.execute(
                """
                SELECT match_id, processed_at, league, home_team, away_team
                FROM match_results
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            for row in rows:
                pairs.append({
                    "match_id": row[0],
                    "kickoff": row[1],
                    "league": row[2],
                    "home_team": row[3],
                    "away_team": row[4],
                })
        except Exception:
            pass
    conn.close()
    return pairs[:limit]


@app.get("/health")
def health():
    db_ok = False
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "ok": db_ok,
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "0.3",
        "features": ["opportunities", "early_goal_hunter", "chaos_index"],
    }


@app.get("/me")
def me(authorization: str | None = Header(default=None)):
    user_id = user_from_auth(authorization)
    entitled = is_entitled(user_id, refresh=True)
    row = get_subscriber_row(user_id) or {}
    prefs = get_prefs(user_id)
    return {
        "app_user_id": user_id,
        "entitled": entitled,
        "entitlement": row.get("entitlement") or ("pro" if entitled else "free"),
        "status": row.get("status") or ("active" if entitled else "free"),
        "expires_at": row.get("expires_at"),
        "product_id": row.get("product_id"),
        "environment": row.get("environment"),
        "prefs": prefs,
    }


@app.get("/me/prefs")
def read_prefs(authorization: str | None = Header(default=None)):
    user_id = user_from_auth(authorization)
    return {"prefs": get_prefs(user_id)}


@app.patch("/me/prefs")
def patch_prefs(
    body: PrefsPatch,
    authorization: str | None = Header(default=None),
):
    user_id = user_from_auth(authorization)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    prefs = save_prefs(user_id, patch)
    return {"prefs": prefs}


@app.get("/opportunities")
def opportunities(
    authorization: str | None = Header(default=None),
    limit: int = 20,
):
    require_pro(authorization)
    limit = max(1, min(limit, 100))
    ranked = rank_opportunities(latest_fixtures(limit=max(limit, 20)))
    return {"count": len(ranked[:limit]), "opportunities": ranked[:limit]}


@app.get("/features/early-goal")
def early_goal_feature(
    authorization: str | None = Header(default=None),
    limit: int = 20,
):
    """Early Goal Hunter segment — floating submenu."""
    require_pro(authorization)
    limit = max(1, min(limit, 50))
    ranked = rank_early_goal_matches(latest_match_pairs(limit=max(limit, 30)))
    return {
        "feature": "early_goal_hunter",
        "count": len(ranked[:limit]),
        "matches": ranked[:limit],
    }


@app.get("/features/chaos")
def chaos_feature(
    authorization: str | None = Header(default=None),
    limit: int = 20,
):
    """Chaos Index segment — floating submenu."""
    require_pro(authorization)
    limit = max(1, min(limit, 50))
    ranked = rank_chaos_matches(latest_match_pairs(limit=max(limit, 30)))
    return {
        "feature": "chaos_index",
        "count": len(ranked[:limit]),
        "matches": ranked[:limit],
    }


@app.post("/webhooks/revenuecat")
async def revenuecat_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
):
    if not webhook_auth_ok(authorization):
        raise HTTPException(401, "Bad webhook auth")
    body = await request.json()
    apply_webhook(body)
    return {"ok": True}
