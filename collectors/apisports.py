"""
Shared api-sports.io (API-Football v3) client for batch collectors.

- Stops cleanly when the daily quota is used up (QuotaExhausted), and keeps a
  reserve (APISPORTS_RESERVE, default 500 calls) so a backfill never starves
  the live results collector or the app's fixture list.
- Waits out the per-minute limit instead of failing.

Env:
  API_FOOTBALL_KEY     required
  APISPORTS_RESERVE    daily calls to leave untouched (default 500)
  APISPORTS_DELAY      seconds between calls (default 1.0)
"""

import os
import time

import requests

from constants import API_FOOTBALL_KEY

BASE_URL = "https://v3.football.api-sports.io"
RESERVE = int(os.environ.get("APISPORTS_RESERVE", "500"))
DELAY = float(os.environ.get("APISPORTS_DELAY", "1.0"))

_state = {"remaining_day": None, "calls": 0}


class QuotaExhausted(RuntimeError):
    """Daily quota used (or down to the reserve) — resume tomorrow."""


class AuthError(RuntimeError):
    """Bad/suspended key or plan does not cover the request."""


class NetworkError(RuntimeError):
    """api-sports unreachable after retries — stop and resume next run."""


NETWORK_RETRIES = 6  # waits 5, 10, 20, 40, 80s between attempts (~2.5 min)


def _get(url, params):
    """
    requests.get with retries on connection drops, timeouts, 5xx and
    truncated/garbled bodies. Returns (response, payload); payload is the
    parsed JSON for a 200, else None.
    """
    wait = 5
    last = None
    for attempt in range(NETWORK_RETRIES):
        try:
            resp = requests.get(
                url,
                headers={"x-apisports-key": API_FOOTBALL_KEY},
                params=params,
                timeout=60,
            )
            if resp.status_code != 200 and resp.status_code < 500:
                return resp, None
            if resp.status_code == 200:
                try:
                    return resp, resp.json()
                except ValueError as exc:
                    last = f"unreadable response body ({exc})"
            else:
                last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = f"{type(exc).__name__}: {exc}"
        if attempt < NETWORK_RETRIES - 1:
            print(f"[api-sports] network problem ({last}); retry in {wait}s")
            time.sleep(wait)
            wait *= 2
    raise NetworkError(last)


def require_key():
    if not API_FOOTBALL_KEY:
        raise SystemExit(
            "API_FOOTBALL_KEY is not set — run: bash deploy/set_env.sh API_FOOTBALL_KEY <key>"
        )


def remaining_today():
    return _state["remaining_day"]


def calls_made():
    return _state["calls"]


def _error_text(errors):
    if isinstance(errors, dict):
        return " ".join(f"{k}: {v}" for k, v in errors.items())
    if isinstance(errors, list):
        return " ".join(str(e) for e in errors)
    return str(errors or "")


def api_get(path, params=None):
    """GET BASE_URL+path; returns the parsed JSON payload."""
    remaining = _state["remaining_day"]
    if remaining is not None and remaining <= RESERVE:
        raise QuotaExhausted(f"{remaining} calls left today (reserve {RESERVE})")

    for attempt in range(4):
        resp, payload = _get(f"{BASE_URL}{path}", params or {})
        _state["calls"] += 1
        day_left = resp.headers.get("x-ratelimit-requests-remaining")
        if day_left is not None:
            try:
                _state["remaining_day"] = int(day_left)
            except ValueError:
                pass
        minute_left = resp.headers.get("X-RateLimit-Remaining")

        if resp.status_code == 429:
            time.sleep(60)
            continue
        if resp.status_code in (401, 403):
            raise AuthError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path}: unexpected response {str(payload)[:200]}")

        errors = payload.get("errors")
        if errors:
            text = _error_text(errors)
            low = text.lower()
            if "request limit for the day" in low or low.startswith("requests"):
                raise QuotaExhausted(text)
            if "ratelimit" in low or "too many requests" in low:
                time.sleep(60)
                continue
            if "token" in low or "access" in low or "subscription" in low or "plan" in low:
                raise AuthError(text)
            raise RuntimeError(text)

        if minute_left is not None and minute_left.strip() == "0":
            time.sleep(60)
        else:
            time.sleep(DELAY)
        return payload
    raise RuntimeError(f"{path}: still rate limited after retries")
