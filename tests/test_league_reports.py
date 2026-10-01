"""League turnaround report + youth-league scout (mocked api-sports)."""

import pytest

from collectors import apisports as af
from collectors import backfill_apisports as bf
from models import fta_path_model as pm
from scripts import league_report as lr
from scripts import league_scout as ls

import test_historical_apisports as h


def _m(league, fh, fa, goals):
    return {"league": league, "fh": fh, "fa": fa, "sides": pm._side_outcomes(goals, fh, fa)}


def test_league_stats_counts_turnarounds():
    ms = [
        _m("A", 2, 2, [(10, 1), (20, 1), (60, 2), (80, 2)]),  # home 2-up, drew -> FTA
        _m("A", 2, 0, [(5, 1), (50, 1)]),                      # home 2-up, won
        _m("B", 0, 0, []),
    ]
    s = lr.league_stats(ms)
    a = s["A"]
    assert a["matches"] == 2 and a["goals"] == 3.0
    assert a["up2"] == 50.0           # 2 of 4 team-sides went 2 up
    assert a["fail"] == 50.0          # 1 of those 2 leads not won
    assert a["fta"] == 25.0           # 1 of 4 team-sides
    assert a["early"] == 100.0        # both matches had a goal by 30'
    assert s["B"]["fta"] == 0.0


def test_scout_probe_uses_validated_goal_timelines(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "SEASONS_CACHE", tmp_path / "seasons.json")
    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "test")
    monkeypatch.setattr(af, "RESERVE", 5)
    af._state.update({"remaining_day": None, "calls": 0})
    monkeypatch.setattr(af, "api_get", h.FakeAPI())
    name, matches = ls.probe(39, season=2024, sample=50)
    # fixture 3's events can't reproduce its 3-0 score -> rejected, like the backfill
    assert len(matches) == 2
    stats = lr.league_stats(matches)
    (only,) = stats.values()
    assert only["matches"] == 2 and only["fta"] == 25.0   # Arsenal 2-0 up then 2-2
