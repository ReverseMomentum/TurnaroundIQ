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


def test_goal_events_must_match_official_score(api, monkeypatch):
    """A goal later ruled out (still listed as a Goal event) must not create a fake 2-0."""
    var = h.fixture(6, "2026-09-02", (h.ARS, "Arsenal"), (h.CHE, "Chelsea"), 1, 1)
    monkeypatch.setitem(h.FIXTURES, 2026, h.FIXTURES[2026] + [var])
    monkeypatch.setitem(h.EVENTS, 6, [h.goal(h.ARS, "Arsenal", 10), h.goal(h.ARS, "Arsenal", 20),
                                      h.goal(h.CHE, "Chelsea", 60)])
    assert rc.process_results(season_to_date=True) == 0
    assert [r[0] for r in rows()] == ["5"]          # the 2-0-that-never-was is not saved
    assert not rc.fixture_already_processed(6)      # so it is retried on the next run
    conn = sqlite3.connect(database.DB_NAME)
    goals = conn.execute("SELECT minute, side FROM live_goals WHERE match_id = '5'").fetchall()
    conn.close()
    assert goals == [(70, 1)]


def test_own_goal_side_resolved_like_backfill(api, monkeypatch):
    og = h.fixture(7, "2026-09-03", (h.LIV, "Liverpool"), (h.EVE, "Everton"), 1, 0)
    monkeypatch.setitem(h.FIXTURES, 2026, h.FIXTURES[2026] + [og])
    monkeypatch.setitem(h.EVENTS, 7, [h.goal(h.EVE, "Everton", 33, detail="Own Goal")])
    rc.process_results(season_to_date=True)
    got = {r[0]: r for r in rows()}
    assert got["7"][2:4] == (1, 0)
