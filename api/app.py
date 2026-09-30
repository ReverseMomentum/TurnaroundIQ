"""
Public API for the mobile app.
"""

from datetime import datetime, timedelta, timezone
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from billing.revenuecat import management_url as revenuecat_management_url
from billing.revenuecat import (
    apply_webhook,
    get_prefs,
    get_subscriber_row,
    is_entitled,
    save_prefs,
    webhook_auth_ok,
    ensure_tables,
)
from constants import API_FOOTBALL_KEY, SUPPORTED_LEAGUE_IDS
from database import create_tables, get_db
from models.opportunities_engine import (
    rank_opportunities,
    build_opportunity,
    get_last_rank_errors,
    filter_opportunities,
    fta_band,
    FTA_BANDS,
)
from models.early_goal_hunter import rank_early_goal_matches
from models.chaos_index import rank_chaos_matches
from models.mismatch_meter import rank_mismatch_matches
from team_normalizer import normalize_team
from ops.health import check as data_health
from collectors import odds_apisports as odds_store
from api import odds_refresh
from api import auth
from urllib.parse import quote

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
UPCOMING_DAYS = int(os.environ.get("UPCOMING_DAYS", "7"))
FIXTURE_CACHE_SECONDS = int(os.environ.get("FIXTURE_CACHE_SECONDS", "1800"))
# Mismatch Meter is weak in backtests — off unless explicitly enabled.
FEATURE_MISMATCH = os.environ.get("FEATURE_MISMATCH", "0") == "1"
# After a failed fixtures fetch, wait this long before calling API-Football again.
FIXTURE_RETRY_SECONDS = int(os.environ.get("FIXTURE_RETRY_SECONDS", "300"))

log = logging.getLogger("turnaroundiq.api")

CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
]

app = FastAPI(title="TurnaroundIQ", version="0.5.6")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_upcoming_cache = {"ts": 0.0, "pairs": []}
_fixture_status = {"source": "none", "error": None, "failed_at": 0.0}


class PrefsPatch(BaseModel):
    default_stake: Optional[float] = None
    default_commission: Optional[float] = None
    risk_warning_pct: Optional[float] = None
    notify_opportunity: Optional[bool] = None
    notify_fixture_starting: Optional[bool] = None
    notify_live_trigger: Optional[bool] = None
    notify_exchange_entry: Optional[bool] = None
    bookmakers: Optional[list[str]] = None  # [] = any UK bookmaker


class TrackedCreate(BaseModel):
    home_team: str
    away_team: str
    team: Optional[str] = None
    is_home: Optional[bool] = True
    league: Optional[str] = ""
    kickoff: Optional[str] = None
    bookmaker: Optional[str] = "Paper"
    back_odds: Optional[float] = None
    lay_odds: Optional[float] = None
    stake: Optional[float] = 40.0
    commission: Optional[float] = 2.0
    fta_pct: Optional[float] = None
    notes: Optional[str] = None
    match_id: Optional[str] = None
    score_with_model: bool = True
    paper: bool = True
    product: Optional[str] = "fta"


class TrackedSettle(BaseModel):
    result: str = Field(description="won|lost|void|fta|no_fta")
    actual_profit: Optional[float] = None
    actual_fta: Optional[int] = None


class TrackedEdit(BaseModel):
    stake: Optional[float] = Field(default=None, gt=0, le=100000)
    back_odds: Optional[float] = Field(default=None, gt=1, le=1000)
    lay_odds: Optional[float] = Field(default=None, gt=1, le=1000)
    commission: Optional[float] = Field(default=None, ge=0, le=20)
    bookmaker: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=200)


class PaperSettingsPatch(BaseModel):
    starting_bankroll: Optional[float] = None
    default_stake: Optional[float] = None
    default_commission: Optional[float] = None


@app.on_event("startup")
def startup():
    create_tables()
    ensure_tables()
    tracked_store.ensure_tracked_tables()
    auth.ensure_auth_tables()
    # Warm the FTA path model's team state (~2s) off the request path.
    import threading
    from models import fta_path_model

    threading.Thread(target=fta_path_model.current_state, daemon=True).start()


def user_from_auth(authorization: str | None) -> str:
    """
    Bearer token -> app user id.
      s_…  web session (email sign-in) -> the account's u_… id
      u_…  refused: web accounts must use a session token
      else RevenueCat app user id from the native app (e.g. $RCAnonymousID:…)
    """
    if not authorization:
        raise HTTPException(401, "Missing Authorization")
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    if token.startswith("s_"):
        try:
            user_id = auth.resolve_session(token)
        except auth.AuthError as exc:
            raise HTTPException(exc.status, exc.message) from exc
        if not user_id:
            raise HTTPException(401, "Session expired — sign in again")
        return user_id
    if token.startswith("u_"):
        raise HTTPException(401, "Sign in required")
    return token


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


class AuthStart(BaseModel):
    email: str


class AuthVerify(BaseModel):
    email: str
    code: str


@app.post("/auth/start")
def auth_start(body: AuthStart, request: Request):
    try:
        auth.start(body.email, _client_ip(request))
    except auth.AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except Exception as exc:
        log.exception("auth/start email failed")
        raise HTTPException(502, "Couldn't send the email — try again shortly") from exc
    return {"ok": True}


@app.post("/auth/verify")
def auth_verify(body: AuthVerify):
    try:
        return auth.verify(body.email, body.code)
    except auth.AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@app.delete("/me")
def delete_me(authorization: str | None = Header(default=None)):
    """Delete this web account and its data (UK GDPR erasure). Subscriptions
    must be cancelled separately with the payment provider."""
    token = (authorization or "").replace("Bearer ", "").strip()
    if not token.startswith("s_"):
        raise HTTPException(400, "Only web accounts can be deleted here")
    user_id = user_from_auth(authorization)
    auth.delete_account(user_id)
    return {"deleted": True}


@app.post("/auth/logout")
def auth_logout(authorization: str | None = Header(default=None)):
    token = (authorization or "").replace("Bearer ", "").strip()
    if token.startswith("s_"):
        auth.logout(token)
    return {"ok": True}


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


def fetch_upcoming_from_api_football(days=UPCOMING_DAYS):
    """Pull not-started fixtures for supported leagues over the next N days."""
    if not API_FOOTBALL_KEY:
        _fixture_status["error"] = "api_football_key_missing"
        return []

    errors = 0
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    pairs = []
    seen = set()
    now = datetime.now(timezone.utc)

    for day in range(max(1, days)):
        target = (now + timedelta(days=day)).strftime("%Y-%m-%d")
        url = (
            "https://v3.football.api-sports.io/fixtures"
            f"?date={target}&status=NS"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=45)
            if resp.status_code == 429:
                time.sleep(8)
                resp = requests.get(url, headers=headers, timeout=45)
            resp.raise_for_status()
            payload = resp.json().get("response") or []
        except Exception as exc:
            errors += 1
            log.warning("api-football fixtures %s failed: %s", target, exc)
            continue

        for fx in payload:
            league_meta = fx.get("league") or {}
            league_id = league_meta.get("id")
            if league_id not in SUPPORTED_LEAGUE_IDS:
                continue
            teams = fx.get("teams") or {}
            home_raw = (teams.get("home") or {}).get("name")
            away_raw = (teams.get("away") or {}).get("name")
            if not home_raw or not away_raw:
                continue
            home = normalize_team(home_raw)
            away = normalize_team(away_raw)
            fixture_meta = fx.get("fixture") or {}
            match_id = str(fixture_meta.get("id") or "")
            kickoff = fixture_meta.get("date") or target
            league = SUPPORTED_LEAGUE_IDS[league_id]
            key = (home, away, str(kickoff))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({
                "match_id": match_id,
                "kickoff": kickoff,
                "league": league,
                "home_team": home,
                "away_team": away,
            })
        time.sleep(0.35)

    _fixture_status["error"] = (
        f"api_football_errors:{errors}/{max(1, days)}" if errors else None
    )
    pairs.sort(key=lambda p: p.get("kickoff") or "")
    return pairs


def _not_kicked_off(pair, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        ko = datetime.fromisoformat(str(pair.get("kickoff")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return ko > now


def upcoming_match_pairs(limit=60):
    """
    Cached upcoming (not started) fixtures. Does NOT use odds_history.

    Never falls back to finished matches: if API-Football is down or out of
    quota we serve the last good list (minus kicked-off games) or nothing.
    """
    global _upcoming_cache
    now = time.time()
    if _upcoming_cache["pairs"] and (now - _upcoming_cache["ts"]) < FIXTURE_CACHE_SECONDS:
        return [p for p in _upcoming_cache["pairs"] if _not_kicked_off(p)][:limit]

    pairs = []
    if (now - _fixture_status["failed_at"]) >= FIXTURE_RETRY_SECONDS:
        pairs = fetch_upcoming_from_api_football()
        if pairs:
            _upcoming_cache = {"ts": now, "pairs": pairs}
            _fixture_status["source"] = "api-football-upcoming"
            _fixture_status["failed_at"] = 0.0
            return pairs[:limit]
        _fixture_status["failed_at"] = now

    stale = [p for p in _upcoming_cache["pairs"] if _not_kicked_off(p)]
    _fixture_status["source"] = "cached-upcoming" if stale else "unavailable"
    return stale[:limit]


def fixture_meta():
    return {
        "fixture_source": _fixture_status["source"],
        "fixture_error": _fixture_status["error"],
    }


def latest_match_pairs(limit=40):
    return upcoming_match_pairs(limit=limit)


def _with_prices(base, row, is_home, bookmakers=None):
    """Best back price (from the user's bookmakers if they've chosen some) + estimated
    exchange lay from collectors/odds_apisports, if fresh."""
    prices = odds_store.side_prices(row, is_home, bookmakers)
    if not prices:
        if row and bookmakers:
            return {**base, "not_at_my_books": True}
        return base
    back, book, lay_est, updated = prices
    others = odds_store.book_prices(row, is_home, bookmakers)[:6]
    return {
        **base,
        "bookmaker": book or "Bookmaker",
        "back_odds": back,
        "lay_odds": lay_est,
        "lay_estimated": True,
        "odds_estimated": False,
        "odds_updated_at": updated,
        "back_prices": [{"bookmaker": n, "back": p} for n, p in others],
    }


def _kicks_off_within(pair, hours, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        ko = datetime.fromisoformat(str(pair.get("kickoff")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return now < ko <= now + timedelta(hours=hours)


def _next_kickoff_after(hours):
    """First supported-league kick-off after the window (for 'nothing in the next 24h' messages)."""
    later = [p for p in upcoming_match_pairs(limit=400)
             if _not_kicked_off(p) and not _kicks_off_within(p, hours)]
    return min((str(p.get("kickoff")) for p in later), default=None)


def fixtures_from_upcoming(limit=40, hours=None, bookmakers=None):
    fixtures = []
    if hours:
        # every game in the window (a Saturday can have 100+), not just the first few
        pairs = [p for p in upcoming_match_pairs(limit=400) if _kicks_off_within(p, hours)]
        limit = max(limit, len(pairs))
    else:
        pairs = upcoming_match_pairs(limit=max(limit, 20))
    stored = odds_store.load_odds([p.get("match_id") for p in pairs])
    for pair in pairs:
        home = pair["home_team"]
        away = pair["away_team"]
        row = stored.get(str(pair.get("match_id")))
        market = {"market_over25": (row or {}).get("over25"), "market_under25": (row or {}).get("under25")}
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
            **market,
        }
        fixtures.append(_with_prices({**base, "team": home, "is_home": True}, row, True, bookmakers))
        fixtures.append(_with_prices({**base, "team": away, "is_home": False}, row, False, bookmakers))
    return fixtures[: limit * 2]


def latest_fixtures(limit=40, hours=None, bookmakers=None):
    return fixtures_from_upcoming(limit=limit, hours=hours, bookmakers=bookmakers)


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
        "bookmaker": body.bookmaker or "Paper",
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


@app.post("/odds/refresh")
def refresh_odds(authorization: str | None = Header(default=None)):
    """Re-price the next 24h of games (Pro). Shared cooldown; poll GET /odds/refresh."""
    require_pro(authorization)
    started, st = odds_refresh.start()
    return {"started": started, **st}


@app.get("/odds/bookmakers")
def odds_bookmakers(authorization: str | None = Header(default=None)):
    """UK bookmakers we have prices from, plus the user's saved selection."""
    user_id = user_from_auth(authorization)
    return {
        "available": (books := odds_store.available_bookmakers())[0],
        "priced": books[1],
        "selected": get_prefs(user_id).get("bookmakers") or [],
    }


@app.get("/odds/refresh")
def refresh_odds_status(authorization: str | None = Header(default=None)):
    require_pro(authorization)
    return odds_refresh.status()


@app.get("/health")
def health():
    """
    200 when the product can serve real intel (status ok|degraded),
    503 when it cannot (empty/missing DB, no model). See ops/health.py.
    """
    report = data_health()
    features = [
            "opportunities",
            "fta_bands",
            "fta_edge_gate",
            "upcoming_fixtures_api_football",
            "tracked",
            "paper_trading",
            "early_goal_hunter",
            "chaos_index",
    ]
    if FEATURE_MISMATCH:
        features.append("mismatch_meter")
    body = {
        "ok": not report["critical"],
        "status": report["status"],
        "critical": report["critical"],
        "warnings": report["warnings"],
        "row_counts": report["row_counts"],
        "results_age_hours": report["results_age_hours"],
        "backup_age_hours": report["backup_age_hours"],
        "time": datetime.now(timezone.utc).isoformat(),
        "version": "0.5.6",
        "model_present": report["model_present"],
        "features": features,
        "fta_bands": [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in FTA_BANDS],
        "default_back_odds": DEFAULT_BACK_ODDS,
        "upcoming_days": UPCOMING_DAYS,
        **fixture_meta(),
    }
    return JSONResponse(body, status_code=503 if report["critical"] else 200)


@app.get("/me")
def me(authorization: str | None = Header(default=None)):
    user_id = user_from_auth(authorization)
    entitled = is_entitled(user_id, refresh=True)
    row = get_subscriber_row(user_id) or {}
    prefs = get_prefs(user_id)
    paper = tracked_store.summary(user_id) if entitled else None
    web_link = os.environ.get("RC_WEB_PURCHASE_LINK", "").strip().rstrip("/")
    purchase_url = (
        f"{web_link}/{quote(user_id, safe='')}"
        if web_link and user_id.startswith("u_") and not entitled else None
    )
    return {
        "app_user_id": user_id,
        "email": auth.email_for(user_id) if user_id.startswith("u_") else None,
        "purchase_url": purchase_url,
        "management_url": revenuecat_management_url(user_id),
        "entitled": entitled,
        "entitlement": row.get("entitlement") or ("pro" if entitled else "free"),
        "status": row.get("status") or ("active" if entitled else "free"),
        "expires_at": row.get("expires_at"),
        "product_id": row.get("product_id"),
        "environment": row.get("environment"),
        "prefs": prefs,
        "paper": paper,
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
    min_fta: Optional[float] = None,
    min_edge_pp: Optional[float] = None,
    band: Optional[str] = None,
    edge_gate_only: bool = False,
    require_real_odds: bool = False,
    hours: Optional[int] = None,
):
    """
    FTA opportunities ranked by model fta_pct.

    hours — only games kicking off in the next N hours (the app uses 24: exchange
            lay liquidity is thin before that, and odds are collected for that window)

    Hardening filters (optional):
      min_fta          — minimum model FTA % (e.g. 5)
      band             — elite_4plus|high_3_4|mid_2_3|low_1_2|micro_under_1 (full-event %)
      min_edge_pp      — model − implied from odds
      edge_gate_only   — only rows that clear default +2pp edge buffer
      require_real_odds — drop estimated default odds
    """
    user_id = require_pro(authorization)
    limit = max(1, min(limit, 100))
    try:
        hours = max(1, min(hours, 168)) if hours else None
        my_books = get_prefs(user_id).get("bookmakers") or None
        fixtures = latest_fixtures(limit=max(limit, 20), hours=hours, bookmakers=my_books)
        ranked = rank_opportunities(fixtures)
        for r in ranked:
            r["source"] = "auto"
            if r.get("bookmaker") == "Estimated":
                r["odds_estimated"] = True
            if "fta_band" not in r:
                r["fta_band"] = fta_band(r.get("fta_pct"))

        games_in_window = len({r.get("match_id") or r.get("match") for r in ranked})
        best_below_floor = max((r.get("fta_pct") or 0 for r in ranked), default=None)
        ranked = filter_opportunities(
            ranked,
            min_fta=min_fta,
            min_edge_pp=min_edge_pp,
            band=band,
            require_real_odds=require_real_odds,
            edge_gate_only=edge_gate_only,
        )

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
                    "fta_band": t.get("fta_band") or fta_band(t.get("fta_pct")),
                    "lay_stake": t["lay_stake"],
                    "liability": t["liability"],
                    "expected_profit": t.get("expected_profit"),
                    "source": "paper" if t.get("paper") else "manual",
                    "tracked_id": t["id"],
                    "status": t["status"],
                    "kickoff": t["kickoff"],
                    "home_team": t["home_team"],
                    "away_team": t["away_team"],
                    "product": t.get("product") or "fta",
                })

        combined = manual + ranked
        return {
            "count": len(combined[:limit]),
            "auto_count": len(ranked),
            "manual_count": len(manual),
            "fixture_count": len(fixtures),
            **fixture_meta(),
            "filters": {
                "min_fta": min_fta,
                "min_edge_pp": min_edge_pp,
                "band": band,
                "edge_gate_only": edge_gate_only,
                "require_real_odds": require_real_odds,
            },
            "paper_summary": tracked_store.summary(user_id),
            "rank_errors": get_last_rank_errors(),
            "window_hours": hours,
            "games_in_window": games_in_window,
            "best_fta_in_window": best_below_floor,
            "next_kickoff": _next_kickoff_after(hours) if hours else None,
            "bookmakers": my_books or [],
            "odds_updated_at": max(
                (r["odds_updated_at"] for r in ranked if r.get("odds_updated_at")), default=None
            ),
            "odds_refresh": odds_refresh.status(),
            "opportunities": combined[:limit],
        }
    except Exception as exc:
        log.exception("GET /opportunities failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "OPPORTUNITIES_FAILED",
                "message": "Could not build opportunities. Please try again shortly.",
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


@app.put("/tracked/{bet_id}")
def tracked_edit(
    bet_id: int,
    body: TrackedEdit,
    authorization: str | None = Header(default=None),
):
    """Correct a tracked bet's stake / prices / commission; profit figures are recomputed."""
    user_id = require_pro(authorization)
    bet = tracked_store.update_tracked(user_id, bet_id, body.model_dump(exclude_none=True))
    if not bet:
        raise HTTPException(404, "Tracked bet not found")
    return bet


@app.delete("/tracked/{bet_id}")
def tracked_delete(bet_id: int, authorization: str | None = Header(default=None)):
    user_id = require_pro(authorization)
    if not tracked_store.delete_tracked(user_id, bet_id):
        raise HTTPException(404, "Tracked bet not found")
    return {"deleted": bet_id}


@app.get("/paper")
def paper_summary(authorization: str | None = Header(default=None)):
    user_id = require_pro(authorization)
    return {
        "mode": "paper",
        "summary": tracked_store.summary(user_id),
        "settings": tracked_store.get_paper_settings(user_id),
    }


@app.patch("/paper/settings")
def paper_settings(
    body: PaperSettingsPatch,
    authorization: str | None = Header(default=None),
):
    user_id = require_pro(authorization)
    settings = tracked_store.save_paper_settings(
        user_id,
        starting_bankroll=body.starting_bankroll,
        default_stake=body.default_stake,
        default_commission=body.default_commission,
    )
    return {"settings": settings, "summary": tracked_store.summary(user_id)}


@app.post("/paper/auto-settle")
def paper_auto_settle(authorization: str | None = Header(default=None)):
    """Settle open paper bets using match_results 2UP/FTA flags."""
    user_id = require_pro(authorization)
    n = tracked_store.auto_settle_from_results(user_id)
    return {"settled": n, "summary": tracked_store.summary(user_id)}


def _feature_pairs(limit, hours):
    """Upcoming fixtures for a feature page: every game in the next `hours`, or the next few."""
    if hours:
        hours = max(1, min(hours, 168))
        return [p for p in upcoming_match_pairs(limit=400) if _kicks_off_within(p, hours)]
    return latest_match_pairs(limit=max(limit, 40))


@app.get("/features/early-goal")
def early_goal_feature(
    authorization: str | None = Header(default=None),
    limit: int = 20,
    hours: Optional[int] = None,
    min_score: Optional[float] = None,
):
    """hours: only games kicking off in the next N hours; min_score: hide Hunter scores below it."""
    require_pro(authorization)
    limit = max(1, min(limit, 50))
    ranked = rank_early_goal_matches(_feature_pairs(limit, hours))
    if min_score is not None:
        ranked = [r for r in ranked if (r.get("hunter_score") or 0) >= min_score]
    return {
        "feature": "early_goal_hunter",
        "count": len(ranked[:limit]),
        **fixture_meta(),
        "matches": ranked[:limit],
    }


@app.get("/features/chaos")
def chaos_feature(
    authorization: str | None = Header(default=None),
    limit: int = 20,
    hours: Optional[int] = None,
    min_score: Optional[float] = None,
):
    """hours: only games kicking off in the next N hours; min_score: hide Chaos indexes below it."""
    require_pro(authorization)
    limit = max(1, min(limit, 50))
    ranked = rank_chaos_matches(_feature_pairs(limit, hours))
    if min_score is not None:
        ranked = [r for r in ranked if (r.get("chaos_index") or 0) >= min_score]
    for row in ranked:
        row["chaos_score"] = row.get("chaos_index")
        comps = row.get("components") or {}
        row["btts_pct"] = comps.get("btts")
        row["over25_pct"] = comps.get("o2_5")
    return {
        "feature": "chaos_index",
        "count": len(ranked[:limit]),
        **fixture_meta(),
        "matches": ranked[:limit],
    }


@app.get("/features/mismatch")
def mismatch_feature(
    authorization: str | None = Header(default=None),
    limit: int = 20,
):
    """Mismatch Meter — underdog / strength-vs-hierarchy ranker."""
    if not FEATURE_MISMATCH:
        raise HTTPException(404, "Not found")
    require_pro(authorization)
    limit = max(1, min(limit, 50))
    pairs = latest_match_pairs(limit=max(limit, 40))
    ranked = rank_mismatch_matches(pairs)
    return {
        "feature": "mismatch_meter",
        "count": len(ranked[:limit]),
        **fixture_meta(),
        "matches": ranked[:limit],
    }


ADMIN_USER_IDS = {
    u.strip() for u in os.environ.get("ADMIN_USER_IDS", "").split(",") if u.strip()
}


@app.get("/model/runs")
def model_runs(authorization: str | None = Header(default=None), limit: int = 20):
    """Training history for the in-app Model Testing page. ADMIN_USER_IDS only."""
    user_id = user_from_auth(authorization)
    if user_id not in ADMIN_USER_IDS:
        raise HTTPException(404, "Not found")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, model_name, version, trained_at, training_rows,
                      brier_score, log_loss, roc_auc, notes
               FROM model_runs ORDER BY id DESC LIMIT ?""",
            (max(1, min(limit, 100)),),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    keys = ["id", "model_name", "version", "trained_at", "training_rows",
            "brier_score", "log_loss", "roc_auc", "notes"]
    return {"runs": [dict(zip(keys, r)) for r in rows]}


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
