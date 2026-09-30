"""FTA path model (V5): point-in-time features, full event = A x B, serving."""

import copy
import random
import sqlite3
from datetime import date, timedelta

import numpy as np
import pytest

import database
from models import fta_path_model as pm


def simulate(seed=7, teams=20, seasons=8):
    """Minute-by-minute league; some teams 'collapse' after going 2 up."""
    rng = random.Random(seed)
    names = [f"Team {i:02d}" for i in range(teams)]
    attack = {n: rng.uniform(-0.35, 0.35) for n in names}
    collapse = {n: rng.choice([1.0, 1.0, 4.0]) for n in names}
    matches, events = [], []
    day = date(2019, 8, 1)
    mid = 0
    for _ in range(seasons):  # noqa: B007
        for h in names:
            for a in names:
                if h == a:
                    continue
                mid += 1
                day += timedelta(days=1)
                lam = {1: np.exp(0.25 + attack[h] - attack[a]) * 1.35,
                       2: np.exp(attack[a] - attack[h]) * 1.35}
                score = {1: 0, 2: 0}
                for minute in range(1, 91):
                    for side, team, opp in ((1, h, a), (2, a, h)):
                        rate = lam[side] / 90
                        other = 3 - side
                        if score[other] - score[side] >= 2:  # trailing by 2+
                            leader = a if side == 1 else h
                            rate *= collapse[leader]
                        if rng.random() < rate:
                            score[side] += 1
                            events.append((f"sim-{mid}", minute, side))
                matches.append((f"sim-{mid}", day.isoformat(), "Sim League",
                                h, a, score[1], score[2]))
    return matches, events


@pytest.fixture
def sim_db(tmp_path, monkeypatch):
    conn = sqlite3.connect(database.DB_NAME)
    for t in ("historical_matches", "historical_events", "match_results"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.execute("""CREATE TABLE historical_matches (match_id TEXT, date TEXT, league TEXT,
        season TEXT, country TEXT, home_team TEXT, away_team TEXT, final_home INTEGER,
        final_away INTEGER, odd_h REAL, odd_d REAL, odd_a REAL)""")
    conn.execute("""CREATE TABLE historical_events (match_id TEXT, minute INTEGER,
        event_type TEXT, event_type2 TEXT, side INTEGER, team TEXT, player TEXT,
        is_goal INTEGER, situation TEXT)""")
    matches, events = simulate()
    conn.executemany("""INSERT INTO historical_matches (match_id, date, league, home_team,
        away_team, final_home, final_away) VALUES (?,?,?,?,?,?,?)""", matches)
    conn.executemany("INSERT INTO historical_events (match_id, minute, side, is_goal) "
                     "VALUES (?,?,?,1)", events)
    conn.commit()
    conn.close()
    monkeypatch.setattr(pm, "MODEL_FILE", tmp_path / "path.pkl")
    monkeypatch.setattr(pm, "_bundle_cache", None)
    pm._state_cache.update(ts=0.0, teams=None, leagues=None)
    return matches


def test_features_never_see_the_match_itself(sim_db):
    matches = pm.load_matches()
    k = len(matches) // 2
    rows_before, _, _ = pm.replay(matches)
    changed = copy.deepcopy(matches)
    changed[k]["fh"], changed[k]["fa"] = 9, 0
    changed[k]["sides"][1]["up2"] = 1
    rows_after, _, _ = pm.replay(changed)
    for side in (0, 1):
        a, b = rows_before[2 * k + side], rows_after[2 * k + side]
        assert {f: a[f] for f in pm.FEATURES} == {f: b[f] for f in pm.FEATURES}
    # …while the home team's next match does learn from it
    home = matches[k]["home"]
    nxt = next(i for i in range(2 * k + 2, len(rows_before)) if rows_before[i]["team"] == home)
    assert rows_before[nxt]["t_2up_rate"] != rows_after[nxt]["t_2up_rate"]


def test_train_predict_full_event_is_product(sim_db):
    pm.train()
    out = pm.predict_fixture("Team 03", "Team 07", "Sim League", True)
    assert out["model_version"] == pm.VERSION
    assert out["fta_pct"] == pytest.approx(
        out["two_up_pct"] * out["fail_given_2up_pct"] / 100, abs=0.02)
    assert 0 < out["fta_pct"] < out["two_up_pct"] < 100
    assert 20 <= out["data_confidence"] <= 85


def test_unknown_team_falls_back_to_league_average(sim_db):
    pm.train()
    out = pm.predict_fixture("Nobody FC", "Team 01", "Sim League", True)
    assert out["data_confidence"] == 20.0
    assert 0 < out["fta_pct"] < 20


def test_no_model_returns_none(sim_db):
    assert pm.predict_fixture("Team 01", "Team 02", "Sim League", True) is None


def test_walk_forward_runs_and_each_stage_learns(sim_db):
    # In this simulated league strong teams go 2-up more but collapse less, so
    # the full event itself is barely predictable; each stage must still learn.
    results = pm.walk_forward(folds=3)
    assert len(results) == 3
    assert np.mean([r["a"]["auc"] for r in results]) > 0.6   # strength -> 2-up
    assert np.mean([r["b"]["auc"] for r in results]) > 0.6   # collapse trait


def test_opportunity_serves_full_event(sim_db):
    from models import opportunities_engine as oe
    pm.train()
    opp = oe.build_opportunity({
        "home_team": "Team 03", "away_team": "Team 07", "team": "Team 03",
        "is_home": True, "league": "Sim League", "back_odds": 2.1,
    })
    assert opp["model_version"] == pm.VERSION
    assert opp["fta_pct"] == pytest.approx(
        opp["two_up_pct"] * opp["fail_given_2up_pct"] / 100, abs=0.02)
    assert opp["fta_band"] == oe.fta_band(opp["fta_pct"])
    assert 20 <= opp["confidence"] <= 85


def test_sub_one_percent_is_not_rescaled():
    from api import tracked
    from models import opportunities_engine as oe
    assert oe.fta_pct_as_percent(0.8) == 0.8
    assert tracked.fta_pct_as_percent(0.8) == 0.8
    assert oe.fta_band(0.8) == "micro_under_1"
    assert oe.fta_band(4.2) == "elite_4plus"
