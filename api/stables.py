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

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from racing import store
from racing.engine import price_race

router = APIRouter(prefix="/stables", tags=["stables"])

CACHE_SECONDS = 300
REFRESH_COOLDOWN_SECONDS = 20  # a forced refresh within this of the last pricing reuses it
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
    }


@router.get("/races")
def stables_races(authorization: str | None = Header(default=None), date: Optional[str] = None,
                  refresh: bool = False):
    """refresh=true re-prices the stored races now instead of serving the 5-minute cache."""
    _require_pro(authorization)
    date = date or datetime.now(timezone.utc).date().isoformat()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    with _lock:
        hit = _cache.get(date)
        max_age = REFRESH_COOLDOWN_SECONDS if refresh else CACHE_SECONDS
        if hit and time.time() - hit[0] < max_age:
            return hit[1]
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
        "races": races,
        "opportunities": opps,
    }
    with _lock:
        _cache[date] = (time.time(), body)
    return body


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
