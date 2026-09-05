"""
Public API for the app front end.

    pip install fastapi uvicorn
    REVENUECAT_SECRET_API_KEY=sk_... REVENUECAT_WEBHOOK_AUTH=... \
      uvicorn api.app:app --host 0.0.0.0 --port 8080

App sends:  Authorization: Bearer <RevenueCat app_user_id>
Webhook:    Authorization header matching REVENUECAT_WEBHOOK_AUTH
"""

from datetime import datetime, timezone
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from billing.revenuecat import apply_webhook, is_entitled, webhook_auth_ok, ensure_tables
from database import get_db, create_tables
from models.opportunities_engine import rank_opportunities

app = FastAPI(title="TurnaroundIQ", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    create_tables()
    ensure_tables()


def user_from_auth(authorization: str | None):
    if not authorization:
        raise HTTPException(401, "Missing Authorization")
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return token


def require_pro(authorization: str | None):
    user_id = user_from_auth(authorization)
    if not is_entitled(user_id):
        raise HTTPException(status_code=402, detail="Subscription required")
    return user_id


def latest_fixtures(limit=40):
    conn = get_db()
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


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.get("/me")
def me(authorization: str | None = Header(default=None)):
    user_id = user_from_auth(authorization)
    entitled = is_entitled(user_id, refresh=True)
    return {"app_user_id": user_id, "entitled": entitled}


@app.get("/opportunities")
def opportunities(
    authorization: str | None = Header(default=None),
    limit: int = 20,
):
    require_pro(authorization)
    ranked = rank_opportunities(latest_fixtures(limit=max(limit, 20)))
    return {"count": len(ranked[:limit]), "opportunities": ranked[:limit]}


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
