"""
The Stables API: extra-place value for horse racing (Pro).

  GET  /stables/races?date=YYYY-MM-DD  every stored race on a date, priced
  POST /stables/price                  price a race typed in by hand
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from collectors import betfair
from racing import store
from racing.engine import price_race

router = APIRouter(prefix="/stables", tags=["stables"])

UK = ZoneInfo("Europe/London")
CACHE_SECONDS = 300
REFRESH_COOLDOWN_SECONDS = 20  # a forced refresh within this of the last pricing reuses it
FEED_COOLDOWN_SECONDS = 120    # Betfair is fetched at most this often from the button
FEED_HOURS = 12
_feed = {"at": 0.0, "result": None, "error": None}


def _fetch_feed() -> None:
    """Pull fresh cards + exchange prices from Betfair (skipped if not set up, recent, or the cron job is running)."""
    if not betfair.configured() or time.time() - _feed["at"] < FEED_COOLDOWN_SECONDS:
        return
    _feed["at"] = time.time()
    try:
        out = betfair.collect_locked(FEED_HOURS, wait=False)
        if out is not None:
            _feed.update(result=out, error=None)
    except Exception as e:  # network / login problems must not break the page
        _feed["error"] = str(e)[:300]


def _feed_status() -> dict:
    return {"source": "betfair" if betfair.configured() else None,
            "last_fetch": store.last_snapshot(), "error": _feed["error"]}
_cache: dict = {}
_lock = threading.Lock()


def _require_pro(authorization):
    from api.app import require_pro  # late import: api.app includes this router

    return require_pro(authorization)


def _calibration_summary(cal: dict) -> dict:
    return {
        "fitted": bool(cal.get("fitted")),
        "n_races": cal.get("n_races") or 0,
        "discounts": cal.get("discounts"),
        "created_at": cal.get("created_at"),
        "learned": ((cal.get("blend") or {}).get("features") or [])[1:] if (cal.get("blend") or {}).get("fitted") else [],
    }


def _started(race: dict, now: datetime) -> bool:
    """True once the race's UK off time has passed (or it was on an earlier day)."""
    today = now.date().isoformat()
    if (race.get("date") or today) != today:
        return (race.get("date") or today) < today
    t = race.get("time")
    return bool(t) and t <= now.strftime("%H:%M")


def _with_live_status(body: dict) -> dict:
    """Mark started races at response time (cached prices can be minutes old)."""
    now = datetime.now(UK)
    races = [{**r, "started": _started(r, now)} for r in body["races"]]
    live = {r["race_id"] for r in races if not r["started"]}
    return {**body, "races": races,
            "opportunities": [o for o in body["opportunities"] if o["race_id"] in live],
            "started_count": len(races) - len(live)}


def _is_admin(user_id: str) -> bool:
    from api.app import ADMIN_USER_IDS

    return user_id in ADMIN_USER_IDS


@router.get("/races")
def stables_races(authorization: str | None = Header(default=None), date: Optional[str] = None,
                  refresh: bool = False):
    """refresh=true re-prices the stored races now instead of serving the 5-minute cache."""
    user_id = _require_pro(authorization)
    return {**_races_body(date, refresh), "can_edit_offers": _is_admin(user_id)}


def _races_body(date: Optional[str], refresh: bool) -> dict:
    date = date or datetime.now(UK).date().isoformat()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    with _lock:
        hit = _cache.get(date)
        max_age = REFRESH_COOLDOWN_SECONDS if refresh else CACHE_SECONDS
        if hit and time.time() - hit[0] < max_age:
            return _with_live_status(hit[1])
    if refresh:
        _fetch_feed()
    cal = store.latest_calibration()
    races = [price_race(r, cal) for r in store.races_on(date)]
    opps = [{**o, "race_id": r["race_id"], "course": r["course"], "time": r["time"],
             "race_name": r["name"], "field_size": r["field_size"]}
            for r in races for o in r["opportunities"]]
    opps.sort(key=lambda o: (o["grade"], -o["each_way_ev"]))
    body = {
        "date": date,
        "priced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dates": store.race_dates(),
        "calibration": _calibration_summary(cal),
        "feed": _feed_status(),
        "races": races,
        "opportunities": opps,
    }
    with _lock:
        _cache[date] = (time.time(), body)
    return _with_live_status(body)


def split_bookmakers(text: str) -> list[str]:
    """'Bet365, Paddy Power,bet365' -> ['Bet365', 'Paddy Power'] (comma-separated, de-duplicated)."""
    out, seen = [], set()
    for name in (text or "").split(","):
        name = name.strip()[:40]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


class OffersIn(BaseModel):
    bookmaker: str = Field(min_length=1, max_length=400)   # one name, or several separated by commas
    places: int = Field(ge=1, le=10)
    fraction: str = Field(default="1/5", max_length=8)
    race_ids: list[int] = Field(min_length=1, max_length=200)


def _require_admin(authorization) -> str:
    user_id = _require_pro(authorization)
    if not _is_admin(user_id):
        raise HTTPException(403, "Only admins can edit extra-place offers")
    return user_id


@router.post("/offers")
def stables_add_offers(body: OffersIn, authorization: str | None = Header(default=None)):
    """Add one bookmaker's extra-place terms to the chosen races (shared with every user)."""
    _require_admin(authorization)
    from racing.extra_place import parse_fraction

    frac = parse_fraction(body.fraction)
    if not frac or frac > 1:
        raise HTTPException(400, "fraction must look like 1/5")
    books = split_bookmakers(body.bookmaker)
    if not books:
        raise HTTPException(400, "bookmaker name needed")
    n = sum(store.set_offers(body.race_ids, b, body.places, frac) for b in books)
    with _lock:
        _cache.clear()
    return {"updated": n, "bookmakers": books, "races": n // len(books)}


@router.delete("/offers")
def stables_delete_offer(race_id: int, bookmaker: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    n = store.delete_offer(race_id, bookmaker)
    with _lock:
        _cache.clear()
    return {"deleted": n}


class TrackIn(BaseModel):
    race_id: int
    horse: str = Field(min_length=1, max_length=60)
    bookmaker: str = Field(min_length=1, max_length=40)
    odds: float = Field(gt=1, le=1001)
    stake: float = Field(gt=0, le=100000)          # total each-way stake (half win, half place)
    places: int = Field(ge=1, le=10)
    fraction: str = Field(default="1/5", max_length=8)
    paper: bool = True


@router.post("/track")
def stables_track(body: TrackIn, authorization: str | None = Header(default=None)):
    """Add an each-way bet to My bets with a snapshot of the model at this moment."""
    user_id = _require_pro(authorization)
    from racing import bets as racing_bets

    try:
        return racing_bets.track(user_id, body.race_id, body.horse, body.bookmaker, body.odds, body.stake,
                                 body.places, body.fraction, body.paper)
    except racing_bets.TrackError as e:
        raise HTTPException(400, str(e))


@router.get("/tracker")
def stables_tracker(authorization: str | None = Header(default=None), paper: Optional[bool] = None):
    """Tracked racing bets: return vs the model's expectation, CLV vs Betfair SP, splits."""
    user_id = _require_pro(authorization)
    from racing import bets as racing_bets

    return racing_bets.report(user_id, paper)


class ManualRunner(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    odds: float = Field(gt=1, le=1001)
    exchange_back: Optional[float] = Field(default=None, gt=1, le=1001)
    exchange_lay: Optional[float] = Field(default=None, gt=1, le=1001)


class ManualTerms(BaseModel):
    bookmaker: str = Field(default="Bookmaker", max_length=40)
    places: int = Field(ge=1, le=10)
    fraction: str = Field(default="1/5", max_length=8)


class ManualRace(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    handicap: bool = False
    race_type: Optional[str] = Field(default=None, pattern="^(flat|hurdle|chase)$")
    runners: list[ManualRunner] = Field(min_length=2, max_length=40)
    terms: list[ManualTerms] = Field(default_factory=list, max_length=8)


@router.post("/price")
def stables_price(body: ManualRace, authorization: str | None = Header(default=None)):
    _require_pro(authorization)
    race = {
        "name": body.name,
        "handicap": body.handicap,
        "race_type": body.race_type,
        "runners": [
            {
                "name": r.name,
                "win_odds": r.odds,
                "exchange": {"back": r.exchange_back, "lay": r.exchange_lay}
                if (r.exchange_back or r.exchange_lay) else None,
            }
            for r in body.runners
        ],
        "terms": [t.model_dump() for t in body.terms],
    }
    cal = store.latest_calibration()
    return {**price_race(race, cal), "calibration": _calibration_summary(cal)}
