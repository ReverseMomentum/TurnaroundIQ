"""
Shared TheStatsAPI client.

Auth: Authorization Bearer.
Base: https://api.thestatsapi.com/api
"""

import time
from datetime import datetime, timedelta, timezone

import requests

from constants import THESTATSAPI_KEY, SUPPORTED_LEAGUES

BASE_URL = "https://api.thestatsapi.com/api"
HEADERS = {
    "Authorization": f"Bearer {THESTATSAPI_KEY}",
    "Accept": "application/json",
}
REQUEST_DELAY = 0.6

# Known IDs so we skip a search call when possible.
KNOWN_COMPETITIONS = {
    "Premier League": "comp_3039",
    "Major League Soccer": "comp_9799",
}

_competition_cache = {}


def api_get(path, params=None):
    url = f"{BASE_URL}{path}"
    response = requests.get(url, headers=HEADERS, params=params or {}, timeout=45)
    if response.status_code == 429:
        retry = int(response.headers.get("Retry-After", "8"))
        print(f"TheStatsAPI 429, sleeping {retry}s")
        time.sleep(retry)
        response = requests.get(url, headers=HEADERS, params=params or {}, timeout=45)
    if response.status_code >= 400:
        print(f"TheStatsAPI {response.status_code} {path}: {response.text[:240]}")
        response.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return response.json()


def unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def find_competition_id(league_name):
    if league_name in _competition_cache:
        return _competition_cache[league_name]
    if league_name in KNOWN_COMPETITIONS:
        _competition_cache[league_name] = KNOWN_COMPETITIONS[league_name]
        return KNOWN_COMPETITIONS[league_name]

    payload = api_get("/football/competitions", {"search": league_name, "per_page": 25})
    rows = unwrap(payload) or []
    if isinstance(rows, dict):
        rows = [rows]

    target = league_name.lower()
    chosen = None
    for row in rows:
        name = (row.get("name") or "").lower()
        if name == target:
            chosen = row.get("id")
            break
    if not chosen and rows:
        chosen = rows[0].get("id")

    _competition_cache[league_name] = chosen
    if chosen:
        print(f"{league_name} -> {chosen}")
    else:
        print(f"No competition id for {league_name}")
    return chosen


def current_season_id(competition_id):
    payload = api_get(f"/football/competitions/{competition_id}/seasons")
    rows = unwrap(payload) or []
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        if row.get("is_current"):
            return row.get("id")
    if rows:
        return rows[0].get("id")
    return None


def list_matches(competition_id, status=None, date_from=None, date_to=None, season_id=None, per_page=50):
    matches = []
    page = 1
    while page <= 6:
        params = {
            "competition_id": competition_id,
            "per_page": per_page,
            "page": page,
        }
        if status:
            params["status"] = status
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if season_id:
            params["season_id"] = season_id

        payload = api_get("/football/matches", params)
        rows = unwrap(payload) or []
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            break
        matches.extend(rows)

        meta = payload.get("meta") if isinstance(payload, dict) else {}
        total_pages = (meta or {}).get("total_pages") or 1
        if page >= total_pages:
            break
        page += 1
    return matches


def match_id_of(match):
    return match.get("id") or match.get("match_id")


def team_name(side):
    if not side:
        return ""
    if isinstance(side, dict):
        return side.get("name") or ""
    return str(side)


def kickoff_of(match):
    return match.get("utc_date") or match.get("kickoff_utc") or ""


def get_match_stats(match_id):
    payload = api_get(f"/football/matches/{match_id}/stats")
    return unwrap(payload) or {}


def get_match_odds(match_id):
    payload = api_get(f"/football/matches/{match_id}/odds")
    return unwrap(payload) or {}


def upcoming_window(days=2):
    now = datetime.now(timezone.utc)
    start = now.strftime("%Y-%m-%d")
    end = (now + timedelta(days=days)).strftime("%Y-%m-%d")
    return start, end


def finished_window(days=21):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    return start, end


def supported_competition_ids():
    mapping = {}
    for name in SUPPORTED_LEAGUES:
        try:
            cid = find_competition_id(name)
        except Exception as exc:
            print(f"Competition lookup failed for {name}: {exc}")
            cid = None
        if cid:
            mapping[name] = cid
    return mapping
