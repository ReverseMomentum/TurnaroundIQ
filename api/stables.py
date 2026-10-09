"""
The Stables API: extra-place value for horse racing (Pro).

  GET  /stables/races?date=YYYY-MM-DD  every stored race on a date, priced
  POST /stables/price                  price a race typed in by hand
"""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Response
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
        "segments": sorted(cal.get("segment_discounts") or {}),
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
            "started_count": len(races) - len(live),
            "refreshing": body.get("date") in _busy}


def _is_admin(user_id: str) -> bool:
    from api.app import ADMIN_USER_IDS

    return user_id in ADMIN_USER_IDS


@router.get("/races")
def stables_races(authorization: str | None = Header(default=None), date: Optional[str] = None,
                  refresh: bool = False):
    """refresh=true re-prices the stored races now instead of serving the 5-minute cache."""
    user_id = _require_pro(authorization)
    date = _check_date(date)
    hit = _serve_entry(date, refresh)
    return Response(_render(hit, _is_admin(user_id)), media_type="application/json")


def _compact(x):
    """Round floats to 5 places (the page shows 1-2): the day's reply is several MB otherwise."""
    if isinstance(x, float):
        return round(x, 5) if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _compact(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_compact(v) for v in x]
    if hasattr(x, "item"):          # numpy scalar
        return _compact(x.item())
    return x


def _dumps(x) -> str:
    return json.dumps(_compact(x), separators=(",", ":"), default=str)


_json: dict = {}   # date -> (id of the cached body, pre-serialised parts)


def _parts(body: dict) -> dict:
    """JSON for a pricing, built once per pricing rather than once per request."""
    key = body.get("date")
    got = _json.get(key)
    if got and got[0] == id(body):
        return got[1]
    head = {k: v for k, v in body.items() if k not in ("races", "opportunities")}
    parts = {
        "head": _dumps(head)[1:-1],
        "races": [(r, _dumps(r)) for r in body["races"]],
        "opps": [(o.get("race_id"), _dumps(o)) for o in body["opportunities"]],
    }
    _json[key] = (id(body), parts)
    return parts


def _render(body: dict, admin: bool) -> str:
    """The races reply: cached JSON plus the per-request bits (started flags, refreshing)."""
    parts = _parts(body)
    now = datetime.now(UK)
    races, live = [], set()
    for r, js in parts["races"]:
        started = _started(r, now)
        if not started:
            live.add(r.get("race_id"))
        races.append('{"started":' + ("true" if started else "false") + ("," + js[1:] if len(js) > 2 else "}"))
    opps = [js for rid, js in parts["opps"] if rid in live]
    return ("{" + parts["head"] + (',' if parts["head"] else '')
            + '"races":[' + ",".join(races) + '],"opportunities":[' + ",".join(opps) + "]"
            + ',"started_count":' + str(len(races) - len(live))
            + ',"refreshing":' + ("true" if body.get("date") in _busy else "false")
            + ',"can_edit_offers":' + ("true" if admin else "false") + "}")


def _price_date(date: str) -> dict:
    """Price every stored race on a date (the slow part: Monte Carlo per race) and cache it."""
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
    _parts(body)
    with _lock:
        _cache[date] = (time.time(), body)
    return body


_busy: set = set()   # dates being re-priced in the background


def _reprice_later(date: str, fetch: bool = False) -> None:
    """Re-price off the request path (one job per date); fetch=True pulls Betfair first."""
    with _lock:
        if date in _busy:
            return
        _busy.add(date)

    def run():
        try:
            if fetch:
                _fetch_feed()
            _price_date(date)
        except Exception:
            pass
        finally:
            with _lock:
                _busy.discard(date)

    threading.Thread(target=run, daemon=True).start()


def _invalidate() -> None:
    """Offers changed: re-price the cached dates now, inside the admin's request,
    so nobody else sees old offers or waits for the pricing."""
    with _lock:
        dates = list(_cache)
        _cache.clear()
    for d in dates:
        try:
            _price_date(d)
        except Exception:
            pass


def _check_date(date: Optional[str]) -> str:
    date = date or datetime.now(UK).date().isoformat()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return date


def _serve_entry(date: str, refresh: bool) -> dict:
    """Always answers from the last pricing when there is one; stale prices (older than
    CACHE_SECONDS) and the Refresh button re-price in the background. The reply says
    "refreshing" while that runs so the page can ask again. Only the very first view
    of a date waits for the pricing."""
    with _lock:
        hit = _cache.get(date)
    if hit:
        age = time.time() - hit[0]
        if refresh and age >= REFRESH_COOLDOWN_SECONDS:
            _reprice_later(date, fetch=True)
        elif age >= CACHE_SECONDS:
            _reprice_later(date)
        return hit[1]
    if refresh:
        _fetch_feed()
    return _price_date(date)


def _races_body(date: Optional[str], refresh: bool) -> dict:
    return _with_live_status(_serve_entry(_check_date(date), refresh))


WARM_SECONDS = 240


def keep_warm() -> None:
    """Background loop (started by api.app): keep today's prices fresh so nobody waits."""
    while True:
        try:
            now = datetime.now(UK)
            if 6 <= now.hour < 23:
                today = now.date().isoformat()
                with _lock:
                    hit = _cache.get(today)
                if not hit or time.time() - hit[0] >= WARM_SECONDS:
                    _price_date(today)
        except Exception:
            pass
        time.sleep(60)


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
    _invalidate()
    return {"updated": n, "bookmakers": books, "races": n // len(books)}


class OffersPasteIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    text: str = Field(min_length=1, max_length=20000)


@router.post("/offers/paste")
def stables_paste_offers(body: OffersPasteIn, authorization: str | None = Header(default=None)):
    """A day's offers pasted as a list ("14:10 Killarney / (4 places, 1/5 odds) / bet365 / Betway (12+)")."""
    _require_admin(authorization)
    from racing import offers_text

    out = offers_text.apply(body.text, body.date)
    _invalidate()
    return out


@router.delete("/offers")
def stables_delete_offer(race_id: int, bookmaker: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    n = store.delete_offer(race_id, bookmaker)
    _invalidate()
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
    lay_pct: float = Field(default=0, ge=0, le=200)  # share of the win lay: 100 covers the win half
    lay_mode: Optional[str] = Field(default=None, pattern="^(none|win|full)$")  # none / part (win) / full (win + place)
    lay_odds: Optional[float] = Field(default=None, gt=1, le=1001)
    place_lay_odds: Optional[float] = Field(default=None, gt=1, le=1001)
    commission: Optional[float] = Field(default=None, ge=0, le=20)


@router.post("/track")
def stables_track(body: TrackIn, authorization: str | None = Header(default=None)):
    """Add an each-way bet to My bets with a snapshot of the model at this moment."""
    user_id = _require_pro(authorization)
    from racing import bets as racing_bets

    try:
        return racing_bets.track(user_id, body.race_id, body.horse, body.bookmaker, body.odds, body.stake,
                                 body.places, body.fraction, body.paper, body.lay_pct, body.lay_odds,
                                 body.commission, body.lay_mode, body.place_lay_odds)
    except racing_bets.TrackError as e:
        raise HTTPException(400, str(e))


class QuoteIn(BaseModel):
    race_id: int
    horse: str = Field(min_length=1, max_length=60)
    bookmaker: str = Field(default="Bookmaker", max_length=40)
    odds: float = Field(gt=1, le=1001)
    places: int = Field(ge=1, le=10)
    fraction: str = Field(default="1/5", max_length=8)


@router.post("/quote")
def stables_quote(body: QuoteIn, authorization: str | None = Header(default=None)):
    """Grade, each-way EV and confidence for one bet at the bettor's price and terms (nothing is saved)."""
    _require_pro(authorization)
    from racing import bets as racing_bets

    try:
        return racing_bets.quote(body.race_id, body.horse, body.bookmaker or "Bookmaker", body.odds,
                                 body.places, body.fraction)
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
