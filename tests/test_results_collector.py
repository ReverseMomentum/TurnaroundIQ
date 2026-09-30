"""Live results collector: season-to-date fill + batched events, mocked api-sports."""

import sqlite3

import pytest

import database
from collectors import apisports as af
from collectors import backfill_apisports as bf
from collectors import results_collector as rc

import test_historical_apisports as h


@pytest.fixture
def api(tmp_path, monkeypatch):
    database_path = database.DB_NAME
    conn = sqlite3.connect(database_path)
    for t in ("match_results", "processed_fixtures", "team_stats"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    conn.close()
    monkeypatch.setattr(bf, "SEASONS_CACHE", tmp_path / "seasons.json")
    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "test")
    monkeypatch.setattr(af, "RESERVE", 5)
    af._state.update({"remaining_day": None, "calls": 0})
    fake = h.FakeAPI()
    monkeypatch.setattr(af, "api_get", fake)
    return fake


def rows():
    conn = sqlite3.connect(database.DB_NAME)
    out = conn.execute(
        "SELECT match_id, home_team, final_home, final_away, match_date FROM match_results"
    ).fetchall()
    conn.close()
    return out


def test_season_to_date_fills_current_season_with_match_dates(api):
    assert rc.process_results(season_to_date=True) == 0
    got = rows()
    # fixture 5 is the only current-season (2026) fixture; listed for every league
    # by the fake API but saved once
    assert [(r[0], r[2], r[3]) for r in got] == [("5", 1, 0)]
    assert got[0][4].startswith("2026-09-01")
    id_calls = [p for path, p in api.calls if "ids" in p]
    assert len(id_calls) == 1


def test_second_run_fetches_no_events(api):
    rc.process_results(season_to_date=True)
    before = len(api.calls)
    assert rc.process_results(season_to_date=True) == 0
    assert not any("ids" in p for _, p in api.calls[before:])
    assert len(rows()) == 1


def test_quota_stop_returns_partial(api):
    af._state["remaining_day"] = 3  # below reserve before anything runs
    assert rc.process_results(season_to_date=True) == rc.EXIT_PARTIAL
