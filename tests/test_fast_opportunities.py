"""Opening the app must not wait for api-sports or a history replay once warm."""

import threading
import time
from datetime import datetime, timedelta, timezone

from api import app as app_module
from models import fta_path_model as pm


def _pairs():
    ko = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    return [{"match_id": "1", "kickoff": ko, "league": "L", "home_team": "A", "away_team": "B"}]


def _reset(monkeypatch, fetch):
    monkeypatch.setattr(app_module, "fetch_upcoming_from_api_football", fetch)
    monkeypatch.setattr(app_module, "_upcoming_cache", {"ts": 0.0, "pairs": []})
    monkeypatch.setattr(app_module, "_fixture_status", {"source": "none", "error": None, "failed_at": 0.0})


def test_stale_list_served_instantly_and_refreshed_in_background(monkeypatch):
    calls = []

    def slow_fetch():
        calls.append(1)
        time.sleep(0.5)
        return _pairs()

    _reset(monkeypatch, slow_fetch)
    app_module._upcoming_cache = {"ts": time.time() - app_module.FIXTURE_CACHE_SECONDS - 5, "pairs": _pairs()}
    t0 = time.time()
    got = app_module.upcoming_match_pairs()
    assert time.time() - t0 < 0.2 and [p["home_team"] for p in got] == ["A"]
    for _ in range(50):          # background refresh lands
        if calls and not app_module._fixture_lock.locked():
            break
        time.sleep(0.05)
    assert len(calls) == 1
    assert time.time() - app_module._upcoming_cache["ts"] < 5


def test_cold_start_downloads_once_for_concurrent_requests(monkeypatch):
    calls = []

    def slow_fetch():
        calls.append(1)
        time.sleep(0.3)
        return _pairs()

    _reset(monkeypatch, slow_fetch)
    results = []
    threads = [threading.Thread(target=lambda: results.append(app_module.upcoming_match_pairs()))
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert all(len(r) == 1 for r in results)


def test_model_state_served_while_rebuilding(monkeypatch):
    builds = []

    def slow_replay(*a, **k):
        builds.append(1)
        time.sleep(0.3)
        return [], {"new": 1}, {}

    monkeypatch.setattr(pm, "load_matches", lambda: [])
    monkeypatch.setattr(pm, "replay", slow_replay)
    monkeypatch.setattr(pm, "_state_cache", {"ts": time.time() - pm.STATE_TTL - 10,
                                             "teams": {"old": 1}, "leagues": {}})
    t0 = time.time()
    teams, _ = pm.current_state()
    assert time.time() - t0 < 0.1 and teams == {"old": 1}   # old state, no wait
    for _ in range(40):
        if pm._state_cache["teams"] == {"new": 1}:
            break
        time.sleep(0.05)
    assert pm._state_cache["teams"] == {"new": 1} and len(builds) == 1
