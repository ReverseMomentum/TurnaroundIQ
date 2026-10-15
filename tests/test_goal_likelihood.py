"""Goal Likelihood (trial): Poisson chances, point-in-time walk, backtest and the API page."""

import math

import numpy as np
import pytest

from models import goal_likelihood as gl


def test_poisson_chances_match_closed_forms():
    p = gl.poisson_chances(1.5, 1.2, 0.3)
    assert p["btts"] == pytest.approx((1 - math.exp(-1.5)) * (1 - math.exp(-1.2)))
    lam = 2.7
    under = math.exp(-lam) * (1 + lam + lam ** 2 / 2)       # total goals ~ Poisson(2.7)
    assert p["over25"] == pytest.approx(1 - under)
    assert p["early"] == pytest.approx(1 - math.exp(-lam * 0.3))
    assert 0 < p["btts_over25"] < min(p["btts"], p["over25"])


def _season(seed=1, seasons=3):
    rng = np.random.default_rng(seed)
    teams = {f"T{i}": (0.6 + 0.05 * i, 1.6 - 0.05 * i) for i in range(20)}
    out, day = [], 738000
    for _ in range(seasons):
        for rnd in range(38):
            names = list(teams)
            rng.shuffle(names)
            for i in range(0, 20, 2):
                h, a = names[i], names[i + 1]
                fh = int(rng.poisson(1.45 * teams[h][0] * teams[a][1]))
                fa = int(rng.poisson(1.15 * teams[a][0] * teams[h][1]))
                goals = sorted([(int(rng.integers(1, 91)), 1) for _ in range(fh)] +
                               [(int(rng.integers(1, 91)), 2) for _ in range(fa)])
                out.append({"day": day, "league": "L", "home": h, "away": a, "fh": fh, "fa": fa,
                            "goals": goals, "sides": {}})
            day += 7
        day += 60
    return out


def test_walk_is_point_in_time():
    matches = _season(seasons=1)
    _, rows = gl.walk(matches)
    assert rows[0][1]["games"] == (0, 0)                     # first game: nothing known yet
    m = rows[-1][0]
    assert max(rows[-1][1]["games"]) < 38                     # never counts its own result


def test_backtest_finds_the_signal_on_synthetic_seasons():
    res = gl.backtest(_season(seasons=4))
    for k in ("btts", "over25"):
        r = res["targets"][k]
        assert r["auc"] > 0.55 and r["logloss"] < r["logloss_base"]
    assert res["top"]["goal score"]["over25"] > res["top"]["all games"]["over25"]


def test_goals_page(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from api import app as app_module

    st, _ = gl.walk(_season(seasons=1))
    monkeypatch.setattr(gl, "current", lambda force=False: (st, {}))
    now = datetime.now(timezone.utc)
    pairs = [{"match_id": "1", "kickoff": (now + timedelta(hours=2)).isoformat(), "league": "L",
              "home_team": "T19", "away_team": "T18"},
             {"match_id": "2", "kickoff": (now + timedelta(hours=3)).isoformat(), "league": "L",
              "home_team": "T0", "away_team": "T1"}]
    monkeypatch.setattr(app_module, "upcoming_match_pairs", lambda limit=60: pairs)
    monkeypatch.setattr(app_module, "require_pro", lambda auth: "u_x")
    out = app_module.goals_feature(authorization="x", limit=50, hours=24)
    assert out["trial"] and [m["match_id"] for m in out["matches"]] == ["1", "2"]   # attacking sides first
    m = out["matches"][0]
    assert 0 < m["btts_pct"] < 100 and m["goal_score"] == pytest.approx(
        0.4 * m["btts_pct"] + 0.4 * m["over25_pct"] + 0.2 * m["early_goal_pct"], abs=0.2)


def test_ltd_profile_who_scores_matters():
    fav = gl.ltd_profile(2.07, 0.98)          # strong home favourite
    assert fav["fav_scores"]["draw"] > fav["lay"] > fav["dog_scores"]["draw"]
    assert fav["fav_scores"]["green"] > 0 > fav["dog_scores"]["green"]
    assert fav["nil_at_exit"]["green"] < 0 and fav["nil_at_exit"]["draw"] < fav["lay"]
    assert 0 < fav["good_goal_pct"] <= fav["goal_before_exit_pct"] <= 100
    even = gl.ltd_profile(1.3, 1.3)
    assert even["dog_scores"]["green"] > 0                 # in an even game either goal helps
    assert gl.draw_chance(1.3, 1.3) == pytest.approx(1 / even["lay"], rel=1e-3)
