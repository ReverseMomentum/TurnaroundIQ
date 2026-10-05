"""FTA path model (V5): point-in-time features, full event = A x B, serving."""

import copy
import random
import sqlite3
from datetime import date, timedelta

import numpy as np
import pytest

import database
from models import fta_path_model as pm


def simulate(seed=7, teams=20, seasons=8, return_strength=False):
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
    if return_strength:
        return matches, events, attack
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


def test_fd_odds_link_and_odds_test(sim_db):
    """Odds priced from true strength link despite name/date noise and help stage A."""
    from collectors import odds_history_fd as fd

    matches, _, attack = simulate(return_strength=True)
    rows = []
    for i, (mid, d, league, h, a, fh, fa) in enumerate(matches):
        diff = attack[h] - attack[a] + 0.12
        ph = 1 / (1 + np.exp(-2.2 * diff)) * 0.75
        pa = (1 - ph) * 0.6
        pd_ = 1 - ph - pa
        day = date.fromisoformat(d) + timedelta(days=1 if i % 7 == 0 else 0)
        rows.append((league, day, h + " FC", a.replace("Team ", "Team-"),
                     "avg", 1.05 / ph, 1.05 / pd_, 1.05 / pa))
    conn = sqlite3.connect(database.DB_NAME)
    stats, n = fd.link(conn, rows)
    conn.close()
    assert n / len(matches) > 0.95
    summary = pm.odds_test(folds=3)
    assert summary["with odds"]["auc_2up"] > summary["without odds"]["auc_2up"]


def test_behaviour_features_present_and_bounded(sim_db):
    rows, teams, _ = pm.replay(pm.load_matches())
    for f in pm.BEHAVIOUR_FEATURES:
        vals = np.array([r[f] for r in rows])
        assert np.isfinite(vals).all(), f
        assert vals.min() >= 0, f
    assert max(r["t_lead_pts"] for r in rows) <= 3.0 + 1e-9
    assert max(r["t_2up_early"] for r in rows) <= 1.0 + 1e-9


def test_live_goal_timeline_feeds_behaviour(sim_db):
    from collectors import results_collector as rc
    conn = sqlite3.connect(database.DB_NAME)
    conn.execute("DROP TABLE IF EXISTS live_goals")
    conn.execute(rc.LIVE_GOALS_DDL)
    conn.execute("""CREATE TABLE IF NOT EXISTS match_results (match_id TEXT, match_date TEXT,
        processed_at TEXT, league TEXT, home_team TEXT, away_team TEXT, final_home INT,
        final_away INT, home_2up INT, away_2up INT, home_lead_minute INT, away_lead_minute INT,
        home_early_goal INT, away_early_goal INT, home_first_half_for INT,
        away_first_half_for INT, home_led INT, away_led INT)""")
    conn.execute("""INSERT INTO match_results VALUES ('live-1', '2031-01-05', NULL, 'Sim League',
        'Live A', 'Live B', 2, 2, 1, 0, 30, 0, 0, 0, 1, 0, 1, 1)""")
    conn.executemany("INSERT INTO live_goals VALUES ('live-1', ?, ?)",
                     [(10, 1), (30, 1), (80, 2), (88, 2)])
    conn.commit()
    conn.close()
    m = [x for x in pm.load_matches() if x["home"] == pm.normalize_team("Live A")][0]
    home, away = m["sides"][1], m["sides"][2]
    assert home["timeline"] == 1 and home["up2"] == 1 and home["minute"] == 30
    assert away["late_for"] == 2 and away["chase_for"] == 2  # both scored while behind, after 75'


def test_platt_calibration_fixes_a_skewed_forecast():
    rng = np.random.default_rng(3)
    true_p = rng.uniform(0.005, 0.05, 40000)
    y = (rng.random(len(true_p)) < true_p).astype(int)
    skewed = np.clip(true_p * 2.5, 0, 0.99)  # model overstates by 2.5x
    ab = pm.platt_fit(y, skewed)
    fixed = pm.platt_apply(ab, skewed)
    assert abs(fixed.mean() - y.mean()) < abs(skewed.mean() - y.mean()) / 5
    assert pm.platt_apply(None, skewed) is not None


def test_train_selects_inputs_and_calibrates(sim_db):
    bundle = pm.train()
    assert bundle["cal_full"] and len(bundle["cal_full"]) == 2
    sel = bundle["selection"]
    assert {"base", "behaviour", "behaviour_used"} <= set(sel)
    assert set(bundle["features"]) >= set(pm.BASE_FEATURES)
    out = pm.predict_fixture("Team 03", "Team 07", "Sim League", True)
    assert out["calibrated"] is True
    assert out["fta_pct"] == pytest.approx(out["two_up_pct"] * out["fail_given_2up_pct"] / 100, abs=0.02)


def test_over_under_variant_only_when_priced(sim_db, monkeypatch):
    from collectors import odds_history_fd as fd
    matches, _, attack = simulate(return_strength=True)
    conn = sqlite3.connect(database.DB_NAME)
    conn.execute("DROP TABLE IF EXISTS match_odds")
    fd.ensure_table(conn)
    rows = []
    for mid, d, league, h, a, fh, fa in matches:
        lam = np.exp(0.25 + attack[h] - attack[a]) * 1.35 + np.exp(attack[a] - attack[h]) * 1.35
        p_under = np.exp(-lam) * (1 + lam + lam ** 2 / 2)
        rows.append((mid, 1.05 / (1 - p_under), 1.05 / p_under))
    conn.executemany("INSERT INTO match_odds (match_id, over25, under25) VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()
    monkeypatch.setattr(pm, "_choose", lambda *a, **k: True)  # force both additions on
    bundle = pm.train()
    assert bundle["ou"] is not None
    assert "mkt_over25" in bundle["ou"]["features"]
    priced = pm.predict_fixture("Team 03", "Team 07", "Sim League", True,
                                market={"over25": 1.8, "under25": 2.0})
    plain = pm.predict_fixture("Team 03", "Team 07", "Sim League", True)
    assert priced["model_version"].endswith("+ou")
    assert not plain["model_version"].endswith("+ou")
    table = pm.compare(folds=3)
    assert [label for label, _ in table][-1] == "priced games: + over/under"


def test_calibration_never_flattens_the_ranking():
    rng = np.random.default_rng(5)
    p = rng.uniform(0.01, 0.06, 20000)
    y = (rng.random(len(p)) < 0.03).astype(int)  # outcome unrelated to p: no ranking skill
    a, b = pm.platt_fit(y, p)
    assert a >= pm.MIN_CAL_SLOPE
    out = pm.platt_apply((a, b), p)
    assert np.all(np.diff(out[np.argsort(p)]) >= -1e-12)  # order preserved
    assert out.std() > 0.001                                # still spread out
    assert abs(out.mean() - y.mean()) < 0.002               # level corrected


def test_recency_weights_halve_per_half_life():
    w = pm.recency_weights([1000, 1365, 1730], half_life=365)
    assert np.allclose(w, [0.25, 0.5, 1.0])
    assert np.allclose(pm.recency_weights([1, 2, 3]), 1.0)  # None -> equal


def test_weighted_calibration_follows_the_recent_rate():
    # Same forecasts throughout; the real rate rises from 1.5% (old) to 3% (recent).
    rng = np.random.default_rng(9)
    days = np.arange(40000, dtype=float)
    p = rng.uniform(0.01, 0.04, len(days))
    rate = np.where(days < 30000, 0.015, 0.03)
    y = (rng.random(len(days)) < rate).astype(int)
    flat = pm.platt_apply(pm.platt_fit(y, p), p).mean()
    recent = pm.platt_apply(pm.platt_fit(y, p, pm.recency_weights(days, 3000)), p).mean()
    assert abs(recent - 0.03) < abs(flat - 0.03)
    assert recent > flat


def test_train_records_recency_choice(sim_db):
    bundle = pm.train()
    assert "recency_half_life_days" in bundle and "cal_half_life_days" in bundle
    assert bundle["recency_half_life_days"] in pm.RECENCY_OPTIONS
    assert bundle["cal_half_life_days"] in pm.RECENCY_OPTIONS
    assert set(bundle["selection"]["recency"]) >= {"equal"}
    pm.walk_forward(folds=3)


def test_h2h_features_point_in_time_and_shrunk(sim_db):
    rows, _, _ = pm.replay(pm.load_matches())
    assert all(k in rows[0] for k in pm.H2H_FEATURES)
    assert rows[0]["h2h_raw_n"] == 0                       # first meeting: nothing known yet
    later = [r for r in rows if r["h2h_raw_n"] > 2]
    assert later and all(0 <= r["h2h_2up"] <= 1 and r["h2h_goals"] > 0 for r in later)
    res = pm.h2h_test()
    assert set(res) == {"current inputs", "+ head-to-head"}
