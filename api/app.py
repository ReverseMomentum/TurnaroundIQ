"""
Public API for the mobile app.
"""

from datetime import datetime, timezone
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
from models.opportunities_engine import (
    rank_opportunities,
    build_opportunity,
    get_last_rank_errors,
)
from models.early_goal_hunter import rank_early_goal_matches
from models.chaos_index import rank_chaos_matches

try:
    from api import tracked as tracked_store
except ImportError:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "tracked", ROOT / "api" / "tracked.py"
    )
    tracked_store = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(tracked_store)

DEFAULT_BACK_ODDS = float(os.environ.get("DEFAULT_BACK_ODDS", "2.10"))

CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
]

app = FastAPI(title="TurnaroundIQ", version="0.5.2")
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


class TrackedCreate(BaseModel):
    home_team: str
    away_team: str
    team: Optional[str] = None
    is_home: Optional[bool] = True
    league: Optional[str] = ""
    kickoff: Optional[str] = None
    bookmaker: Optional[str] = "Manual"
    back_odds: Optional[float] = None
    lay_odds: Optional[float] = None
    stake: Optional[float] = 40.0
    commission: Optional[float] = 2.0
    fta_pct: Optional[float] = None
    notes: Optional[str] = None
    match_id: Optional[str] = None
    score_with_model: bool = True


class TrackedSettle(BaseModel):
    result: str = Field(description="won|lost|void|fta|no_fta")
    actual_profit: Optional[float] = None
    actual_fta: Optional[int] = None


@app.on_event("startup")
def startup():
    create_tables()
    ensure_tables()
    tracked_store.ensure_tracked_tables()


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


def latest_match_pairs(limit=40):
    conn = get_db()
    pairs = []
    seen = set()

    def add(match_id, kickoff, league, home, away):
        if not home or not away:
            return
        key = (str(home), str(away), str(kickoff or ""), str(league or ""))
        if key in seen:
            return
        seen.add(key)
        pairs.append({
            "match_id": match_id,
            "kickoff": kickoff,
            "league": league or "",
            "home_team": home,
            "away_team": away,
        })

    queries = [
        """
        SELECT match_id, kickoff, league, home_team, away_team
        FROM odds_history
        WHERE home_team IS NOT NULL AND away_team IS NOT NULL
        GROUP BY home_team, away_team, IFNULL(kickoff, ''), IFNULL(league, '')
        ORDER BY MAX(id) DESC LIMIT ?
        """,
        """
        SELECT match_id, processed_at, league, home_team, away_team
        FROM match_results
        ORDER BY id DESC LIMIT ?
        """,
        """
        SELECT id, date, NULL, home_team, away_team
        FROM historical_matches
        ORDER BY date DESC LIMIT ?
        """,
    ]
    for sql in queries:
        if len(pairs) >= limit:
            break
        try:
            rows = conn.execute(sql, (limit,)).fetchall()
            for row in rows:
                add(row[0], row[1], row[2], row[3], row[4])
        except Exception:
            continue
    conn.close()
    return pairs[:limit]


def fixtures_from_odds(limit=40):
    conn = get_db()
    fixtures = []
    try:
        rows = conn.execute(
            """
            SELECT match_id, kickoff, league, home_team, away_team,
                   selection, bookmaker, back_odds, lay_odds
            FROM odds_history
            WHERE id IN (
                SELECT MAX(id) FROM odds_history GROUP BY match_id, selection
            )
            ORDER BY kickoff DESC LIMIT ?
            """,
            (limit * 2,),
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
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
            "bookmaker": book or "Book",
            "back_odds": back,
            "lay_odds": lay,
            "odds_estimated": False,
        })
    return fixtures[:limit]


def fixtures_without_odds(limit=40):
    fixtures = []
    for pair in latest_match_pairs(limit=max(limit, 20)):
        home = pair["home_team"]
        away = pair["away_team"]
        base = {
            "match_id": pair.get("match_id"),
            "match": f"{home} vs {away}",
            "kickoff": pair.get("kickoff"),
            "league": pair.get("league") or "",
            "home_team": home,
            "away_team": away,
            "bookmaker": "Estimated",
            "back_odds": DEFAULT_BACK_ODDS,
            "lay_odds": None,
            "odds_estimated": True,
        }
        fixtures.append({**base, "team": home, "is_home": True})
        fixtures.append({**base, "team": away, "is_home": False})
    return fixtures[: limit * 2]


def latest_fixtures(limit=40):
    with_odds = fixtures_from_odds(limit=limit)
    if len(with_odds) >= 3:
        return with_odds
    seen = {(f.get("match_id"), f.get("team")) for f in with_odds}
    for f in fixtures_without_odds(limit=limit):
        key = (f.get("match_id"), f.get("team"))
        if key in seen:
            continue
        with_odds.append(f)
        seen.add(key)
        if len(with_odds) >= limit * 2:
            break
    return with_odds


def score_manual_fixture(body: TrackedCreate):
    team = body.team or body.home_team
    back = body.back_odds if body.back_odds is not None else DEFAULT_BACK_ODDS
    fixture = {
        "match_id": body.match_id or f"manual-{body.home_team}-{body.away_team}",
        "match": f"{body.home_team} vs {body.away_team}",
        "kickoff": body.kickoff,
        "league": body.league or "",
        "home_team": body.home_team,
        "away_team": body.away_team,
        "team": team,
        "is_home": body.is_home if body.is_home is not None else (team == body.home_team),
        "bookmaker": body.bookmaker or "Manual",
        "back_odds": back,
        "lay_odds": body.lay_odds,
        "odds_estimated": body.back_odds is None,
    }
    try:
        return build_opportunity(
            fixture, stake=body.stake or 40, commission=body.commission or 2
        )
    except Exception:
        return None


@app.get("/health")
def health():
    db_ok = False
    model_ok = False
    model_path = str(ROOT / "fta_model.pkl")
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        pass
    try:
        model_ok = (ROOT / "fta_model.pkl").is_file()
    except Exception:
        pass
    return {
        "ok": db_ok,
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "0.5.2",
        "model_present": model_ok,
        "model_path": model_path,
        "features": [
            "opportunities",
            "opportunities_odds_bypass",
            "tracked",
            "early_goal_hunter",
            "chaos_index",
        ],
        "default_back_odds": DEFAULT_BACK_ODDS,
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
    include_tracked: bool = True,
):
    user_id = require_pro(authorization)
    limit = max(1, min(limit, 100))
    try:
        fixtures = latest_fixtures(limit=max(limit, 20))
        ranked = rank_opportunities(fixtures)
        for r in ranked:
            r["source"] = "auto"
            if r.get("estimated_lay") or r.get("bookmaker") == "Estimated":
                r["odds_estimated"] = True

        manual = []
        if include_tracked:
            for t in tracked_store.list_tracked(user_id, status="open", limit=limit):
                manual.append({
                    "match": t["match"],
                    "team": t["team"],
                    "league": t["league"],
                    "bookmaker": t["bookmaker"],
                    "back_odds": t["back_odds"],
                    "lay_odds": t["lay_odds"],
                    "estimated_lay": t["estimated_lay"],
                    "odds_estimated": t["back_odds"] is None,
                    "stake": t["stake"],
                    "commission": t["commission"],
                    "fta_pct": t["fta_pct"],
                    "lay_stake": t["lay_stake"],
                    "liability": t["liability"],
                    "source": "manual",
                    "tracked_id": t["id"],
                    "status": t["status"],
                    "kickoff": t["kickoff"],
                    "home_team": t["home_team"],
                    "away_team": t["away_team"],
                })

        combined = manual + ranked
        return {
            "count": len(combined[:limit]),
            "auto_count": len(ranked),
            "manual_count": len(manual),
            "fixture_count": len(fixtures),
            "rank_errors": get_last_rank_errors(),
            "opportunities": combined[:limit],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(exc),
                "type": type(exc).__name__,
                "trace": traceback.format_exc()[-1500:],
            },
        ) from exc


@app.get("/tracked")
def tracked_list(
    authorization: str | None = Header(default=None),
    status: Optional[str] = None,
    limit: int = 50,
):
    user_id = require_pro(authorization)
    items = tracked_store.list_tracked(user_id, status=status, limit=limit)
    return {
        "count": len(items),
        "summary": tracked_store.summary(user_id),
        "bets": items,
    }


@app.post("/tracked")
def tracked_create(
    body: TrackedCreate,
    authorization: str | None = Header(default=None),
):
    user_id = require_pro(authorization)
    payload = body.model_dump()
    if body.score_with_model and body.fta_pct is None:
        scored = score_manual_fixture(body)
        if scored:
            payload["fta_pct"] = scored.get("fta_pct")
            payload["lay_stake"] = scored.get("lay_stake")
            payload["liability"] = scored.get("liability")
            if payload.get("lay_odds") is None:
                payload["lay_odds"] = scored.get("lay_odds")
            if payload.get("back_odds") is None:
                payload["back_odds"] = scored.get("back_odds")
    try:
        bet = tracked_store.create_tracked(user_id, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return bet


@app.patch("/tracked/{bet_id}")
def tracked_settle(
    bet_id: int,
    body: TrackedSettle,
    authorization: str | None = Header(default=None),
):
    user_id = require_pro(authorization)
    bet = tracked_store.settle_tracked(
        user_id,
        bet_id,
        result=body.result,
        actual_profit=body.actual_profit,
        actual_fta=body.actual_fta,
    )
    if not bet:
        raise HTTPException(404, "Tracked bet not found")
    return bet


@app.get("/features/early-goal")
def early_goal_feature(
    authorization: str | None = Header(default=None),
    limit: int = 20,
):
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
