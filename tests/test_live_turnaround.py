"""Live turnaround model: in-play P(no win) once a team has been 2 goals up."""

import pytest

from models import live_turnaround as lt
from tests.test_fta_path_model import sim_db  # noqa: F401  (fixture)


def test_side_states_start_at_two_up_and_track_the_score():
    goals = [(10, 1), (23, 1), (50, 2), (88, 2)]
    states = lt.side_states(goals, 1)
    assert states[0] == (23, 2, 0)                      # the 2-up moment
    assert (50, 2, 1) in states                          # right after the reply
    assert (45, 2, 0) in states and (55, 2, 1) in states  # 5-minute grid
    assert all(m <= lt.LAST_MINUTE for m, *_ in states[1:])
    assert lt.side_states(goals, 2) == []                # never 2 up


def test_state_features_buckets_and_time():
    f = lt.state_features({"t_fail_rate": 0.1}, 30, 2, 1)
    assert f["d_1"] == 1.0 and f["d_2"] == 0.0
    assert f["rem"] == pytest.approx(60 / 90) and f["d_1_rem"] == pytest.approx(60 / 90)
    assert f["t_fail_rate_rem"] == pytest.approx(0.1 * 60 / 90)
    assert set(lt.FEATURES) <= set(f)
    assert lt.state_features({}, 120, 5, 0)["rem"] == 0.0


def test_train_and_predict_make_football_sense(sim_db, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(lt, "MODEL_FILE", tmp_path / "live.pkl")
    lt._bundle_cache.update(bundle=None, mtime=None)
    bundle = lt.train()
    assert bundle["states"] > 1000 and "beats_table" in bundle["check"]
    p = lambda m, a, b: lt.predict_live("Team 03", "Team 07", "Sim League", True, m, a, b)["no_win_pct"]
    assert p(85, 2, 0) < p(20, 2, 0)      # less time to collapse
    assert p(80, 3, 0) < p(80, 2, 1)      # bigger lead is safer
    out = lt.predict_live("Team 03", "Team 07", "Sim League", True, 60, 2, 0)
    assert 0 < out["no_win_pct"] < 100 and out["win_pct"] == pytest.approx(100 - out["no_win_pct"], abs=0.11)


def test_no_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(lt, "MODEL_FILE", tmp_path / "missing.pkl")
    lt._bundle_cache.update(bundle=None, mtime=None)
    assert lt.predict_live("A", "B", "L", True, 30, 2, 0) is None


def test_endpoint_validates_and_reports_missing_model(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from api import app as app_module
    monkeypatch.setattr(app_module, "require_pro", lambda a: "u_x")
    monkeypatch.setattr(lt, "MODEL_FILE", tmp_path / "missing.pkl")
    lt._bundle_cache.update(bundle=None, mtime=None)
    with pytest.raises(HTTPException) as e:
        app_module.live_turnaround("A", "B", 200, 2, 0, authorization="x")
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        app_module.live_turnaround("A", "B", 30, 2, 0, authorization="x")
    assert e.value.status_code == 503
