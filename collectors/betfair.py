#!/usr/bin/env python3
"""
The Stables: UK + Irish race cards and exchange win prices from the Betfair
Exchange API (a free "delayed" app key is enough: prices lag by seconds).

    python -u collectors/betfair.py --check        # log in, count today's races
    python -u collectors/betfair.py --hours 12     # load races starting in the next 12h

Needs in /etc/turnaroundiq.env (bash deploy/set_env.sh KEY VALUE):
    BETFAIR_APP_KEY, BETFAIR_USERNAME, BETFAIR_PASSWORD

For every WIN market: course, off time, race name, race type, handicap flag,
runners (cloth number, draw, jockey, trainer, age, weight, rating, form),
non-runners, and best back / lay / matched volume per runner. Each run adds a
new price snapshot (racing/store.py). Bookmaker odds and extra-place offers are
not on Betfair: the app shows the lowest bookmaker price worth taking instead.

The session token is cached in logs/betfair_session.json and reused for 3 hours.
Runs under logs/betfair.lock, shared with the app's "Refresh races" button.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import env_loader  # noqa: E402
from racing import store  # noqa: E402

env_loader.load()

LOGIN_URL = "https://identitysso.betfair.com/api/login"
API_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"
SESSION_FILE = ROOT / "logs" / "betfair_session.json"
LOCK_FILE = ROOT / "logs" / "betfair.lock"
SESSION_MAX_AGE = 3 * 3600
UK = ZoneInfo("Europe/London")
HORSE_RACING = "7"
CATALOGUE_PAGE = 100     # MARKET_DESCRIPTION + RUNNER_METADATA cost 2 points each, limit 200
BOOK_PAGE = 40           # EX_BEST_OFFERS costs 5 points per market, limit 200


class BetfairError(RuntimeError):
    pass


def configured() -> bool:
    return all(os.environ.get(k, "").strip() for k in ("BETFAIR_APP_KEY", "BETFAIR_USERNAME", "BETFAIR_PASSWORD"))


USER_AGENT = "TurnaroundIQ/1.0 (+https://turnaroundiq.co.uk)"


def _blocked_hint(status: int) -> str:
    if status == 403:
        return (" HTTP 403 means Betfair's firewall refused this server before checking the login: "
                "usually the server's country or hosting network. Check with: curl -s https://ipinfo.io/country")
    return ""


class Client:
    def __init__(self, http=None):
        if http is None:
            http = requests.Session()
            http.headers["User-Agent"] = USER_AGENT
        self.http = http
        self.app_key = os.environ.get("BETFAIR_APP_KEY", "").strip()
        self.token = None

    def login(self, force: bool = False) -> str:
        if not configured():
            raise BetfairError("Betfair is not set up: BETFAIR_APP_KEY, BETFAIR_USERNAME and BETFAIR_PASSWORD are needed")
        if not force and SESSION_FILE.exists():
            try:
                saved = json.loads(SESSION_FILE.read_text())
                if time.time() - saved["at"] < SESSION_MAX_AGE and saved.get("app_key") == self.app_key:
                    self.token = saved["token"]
                    return self.token
            except (ValueError, KeyError, OSError):
                pass
        r = self.http.post(
            LOGIN_URL,
            data={"username": os.environ["BETFAIR_USERNAME"].strip(), "password": os.environ["BETFAIR_PASSWORD"]},
            headers={"X-Application": self.app_key, "Accept": "application/json",
                     "Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        try:
            body = r.json()
        except ValueError:
            raise BetfairError(f"login: HTTP {r.status_code}, not JSON: {r.text[:80]!r}." + _blocked_hint(r.status_code))
        if body.get("status") != "SUCCESS" or not body.get("token"):
            raise BetfairError(f"login refused: {body.get('error') or body}")
        self.token = body["token"]
        SESSION_FILE.parent.mkdir(exist_ok=True)
        SESSION_FILE.write_text(json.dumps({"token": self.token, "at": time.time(), "app_key": self.app_key}))
        os.chmod(SESSION_FILE, 0o600)
        return self.token

    def call(self, method: str, params: dict, _retry: bool = True):
        if not self.token:
            self.login()
        r = self.http.post(
            API_URL,
            json={"jsonrpc": "2.0", "method": f"SportsAPING/v1.0/{method}", "params": params, "id": 1},
            headers={"X-Application": self.app_key, "X-Authentication": self.token,
                     "Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        try:
            body = r.json()
        except ValueError:
            raise BetfairError(f"{method}: HTTP {r.status_code}, not JSON: {r.text[:80]!r}." + _blocked_hint(r.status_code))
        if "error" in body:
            err = json.dumps(body["error"])
            if _retry and ("INVALID_SESSION" in err or "NO_SESSION" in err):
                self.login(force=True)
                return self.call(method, params, _retry=False)
            raise BetfairError(f"{method}: {err[:300]}")
        return body["result"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def win_markets(client: Client, hours: float, now: datetime | None = None) -> list[dict]:
    """Every GB/IE horse racing WIN market starting within `hours`, paged by start time."""
    now = now or datetime.now(timezone.utc)
    until = now + timedelta(hours=hours)
    out, seen, start = [], set(), now
    for _ in range(20):
        page = client.call("listMarketCatalogue", {
            "filter": {"eventTypeIds": [HORSE_RACING], "marketCountries": ["GB", "IE"],
                       "marketTypeCodes": ["WIN"],
                       "marketStartTime": {"from": _iso(start), "to": _iso(until)}},
            "marketProjection": ["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION",
                                 "RUNNER_DESCRIPTION", "RUNNER_METADATA"],
            "sort": "FIRST_TO_START",
            "maxResults": CATALOGUE_PAGE,
        })
        new = [m for m in page if m["marketId"] not in seen]
        for m in new:
            seen.add(m["marketId"])
        out.extend(new)
        if len(page) < CATALOGUE_PAGE or not new:
            break
        start = datetime.fromisoformat(page[-1]["marketStartTime"].replace("Z", "+00:00"))
    return out


def books(client: Client, market_ids: list[str]) -> dict:
    out = {}
    for i in range(0, len(market_ids), BOOK_PAGE):
        for b in client.call("listMarketBook", {
            "marketIds": market_ids[i:i + BOOK_PAGE],
            "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
        }):
            out[b["marketId"]] = b
    return out


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _int(v):
    x = _num(v)
    return int(x) if x is not None else None


def _race_type(market: dict) -> str:
    desc = (market.get("description") or {}).get("raceType") or ""
    name = market.get("marketName") or ""
    text = f"{desc} {name}".lower()
    if "chase" in text or " chs" in text:
        return "chase"
    if "hurdle" in text or " hrd" in text:
        return "hurdle"
    return "flat"


def to_card(markets: list[dict], book_by_id: dict, timestamp: str) -> dict:
    """Betfair catalogue + books -> the card format racing/store.import_card reads."""
    races = []
    for m in markets:
        start = datetime.fromisoformat(m["marketStartTime"].replace("Z", "+00:00")).astimezone(UK)
        event = m.get("event") or {}
        book = book_by_id.get(m["marketId"]) or {}
        prices = {r["selectionId"]: r for r in book.get("runners") or []}
        name = m.get("marketName") or ""
        runners = []
        for r in m.get("runners") or []:
            md = r.get("metadata") or {}
            p = prices.get(r["selectionId"]) or {}
            ex = p.get("ex") or {}
            back = (ex.get("availableToBack") or [{}])[0].get("price")
            lay = (ex.get("availableToLay") or [{}])[0].get("price")
            horse = (r.get("runnerName") or "").split(". ", 1)[-1] if r.get("runnerName", "")[:1].isdigit() \
                else r.get("runnerName")
            runners.append({
                "horse": horse,
                "number": _int(md.get("CLOTH_NUMBER")),
                "draw": _int(md.get("STALL_DRAW")),
                "jockey": md.get("JOCKEY_NAME"),
                "trainer": md.get("TRAINER_NAME"),
                "age": _int(md.get("AGE")),
                "weight": md.get("WEIGHT_VALUE"),
                "official_rating": _int(md.get("OFFICIAL_RATING")),
                "form": md.get("FORM"),
                "non_runner": p.get("status") == "REMOVED",
                "exchange": {"back": back, "lay": lay, "volume": _num(p.get("totalMatched"))}
                if (back or lay) else None,
            })
        races.append({
            "id": f"bf:{m['marketId']}",
            "date": start.date().isoformat(),
            "time": start.strftime("%H:%M"),
            "course": event.get("venue") or (event.get("name") or "").split(" ")[0],
            "country": event.get("countryCode"),
            "name": name,
            "handicap": "hcap" in name.lower() or "handicap" in name.lower(),
            "race_type": _race_type(m),
            "runners": runners,
        })
    return {"timestamp": timestamp, "races": races}


def collect(hours: float = 12, client: Client | None = None) -> dict:
    """Fetch and store. Returns a summary; raises BetfairError on login / API problems."""
    client = client or Client()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    markets = win_markets(client, hours)
    book_by_id = books(client, [m["marketId"] for m in markets])
    card = to_card(markets, book_by_id, ts)
    summary = store.import_card(card) if card["races"] else {"races": 0, "runners": 0, "results": 0}
    store.prune_snapshots()
    priced = sum(1 for r in card["races"] if r["runners"] and all(x["exchange"] for x in r["runners"]
                                                                   if not x["non_runner"]))
    return {**summary, "fully_priced": priced, "at": ts}


def collect_locked(hours: float = 12, wait: bool = False) -> dict | None:
    """collect() under the shared lock; None if another run holds it and wait is False."""
    LOCK_FILE.parent.mkdir(exist_ok=True)
    with open(LOCK_FILE, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            return None
        return collect(hours)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=12)
    ap.add_argument("--check", action="store_true", help="log in and count races only")
    a = ap.parse_args()
    try:
        if a.check:
            c = Client()
            c.login(force=True)
            print("login OK")
            ms = win_markets(c, 24)
            print(f"{len(ms)} UK/IE win markets in the next 24h")
            for m in ms[:5]:
                print(" ", m["marketStartTime"], (m.get("event") or {}).get("venue"), m.get("marketName"),
                      f"{len(m.get('runners') or [])} runners")
            return
        out = collect_locked(a.hours, wait=True)
        print(json.dumps(out))
    except BetfairError as e:
        print(f"Betfair: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
