"""The Stables: extra-place value model (racing/)."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from racing import calibrate, confidence, kelly, market, positions, store
from racing.engine import price_race
from racing.extra_place import Terms, evaluate, parse_fraction, place_odds, standard_terms

ODDS = [3.5, 4.5, 6, 8, 10, 12, 15, 20, 25, 33, 40, 50]


def test_power_devig_sums_to_one_and_shrinks_longshots_most():
    p = market.devig_power(ODDS)
    assert p.sum() == pytest.approx(1.0)
    raw = np.array([1 / o for o in ODDS])
    mult = raw / raw.sum()
    assert p[0] > mult[0] and p[-1] < mult[-1]


def test_exchange_midpoint_preferred_when_complete():
    runners = [{"win_odds": 2.0, "exchange": {"back": 2.2, "lay": 2.3}},
               {"win_odds": 2.0, "exchange": {"back": 1.9, "lay": 2.0}}]
    p, source, _ = market.fair_win_probs(runners)
    assert source == "exchange" and p.sum() == pytest.approx(1.0) and p[1] > p[0]
    runners[0]["exchange"] = None
    assert market.fair_win_probs(runners)[1] == "bookmaker"


def test_simulation_matches_exact_discounted_harville():
    p = market.devig_power([2.5, 4, 6, 9, 15, 26])
    disc = positions.DEFAULT_DISCOUNTS
    exact = positions.exact_positions(p, disc)
    sim = positions.simulate(p, n_sims=40_000, discounts=disc, seed=3)
    assert np.abs(sim["P"] - exact).max() < 0.012
    assert sim["P"].sum(axis=1) == pytest.approx(np.ones(6))
    assert sim["P"].sum(axis=0) == pytest.approx(np.ones(6))


def test_harville_first_place_is_win_probability():
    p = market.devig_power([2.5, 4, 6, 9, 15])
    exact = positions.exact_positions(p, [1.0])
    assert exact[:, 0] == pytest.approx(p)


def test_discounts_push_outsiders_into_minor_places():
    p = market.devig_power(ODDS)
    harville = positions.simulate(p, discounts=[1.0])["top"][:, 4]
    disc = positions.simulate(p)["top"][:, 4]
    assert disc[-1] > harville[-1] and disc[0] < harville[0]


def test_terms_and_fractions():
    assert standard_terms(4) == (1, 0.0)
    assert standard_terms(7) == (2, 0.25)
    assert standard_terms(10) == (3, 0.2)
    assert standard_terms(14, handicap=True) == (3, 0.25)
    assert standard_terms(18, handicap=True) == (4, 0.25)
    assert parse_fraction("1/5") == 0.2 and parse_fraction(4) == 0.25 and parse_fraction("0.2") == 0.2
    assert place_odds(11, 0.2) == pytest.approx(3.0)


def test_evaluate_extra_place_numbers():
    top = [0.10, 0.20, 0.30, 0.38, 0.45, 0.50]
    ev = evaluate(0.10, top, 11.0, Terms("B", 5, 0.2, 3))
    assert ev["market_probability"] == pytest.approx(1 / 3)
    assert ev["model_probability"] == pytest.approx(0.45)
    assert ev["extra_place_probability"] == pytest.approx(0.15)
    assert ev["place_ev"] == pytest.approx(0.45 * 3 - 1)
    assert ev["win_ev"] == pytest.approx(0.1)
    assert ev["each_way_ev"] == pytest.approx(0.5 * (0.1 + 0.35))


def test_kelly():
    assert kelly.kelly_binary(0.5, 3.0) == pytest.approx(0.25)
    assert kelly.kelly_binary(0.3, 3.0) == 0.0
    assert kelly.kelly_each_way(0.05, 0.2, 11, 3.0) == 0.0
    f = kelly.kelly_each_way(0.10, 0.45, 11, 3.0)
    assert 0 < f < 0.5
    s = kelly.robust_stakes(0.10, 0.45, 0.0, 0.0, 11, 3.0)
    assert s["quarter"]["each_way_pct"] <= s["half"]["each_way_pct"] <= s["full"]["each_way_pct"] <= 5.0
    wide = kelly.robust_stakes(0.10, 0.45, 0.05, 0.15, 11, 3.0)
    assert wide["full"]["each_way_pct"] < s["full"]["each_way_pct"]


def test_grade_rules():
    assert confidence.grade(0.2, 0.05, 80, 1.0, calibrated=False) == "B"
    assert confidence.grade(0.2, 0.05, 80, 1.0, calibrated=True) == "A"
    assert confidence.grade(0.2, -0.01, 80, 1.0, calibrated=True) == "C"
    assert confidence.grade(-0.01, 0.05, 80, 1.0, calibrated=True) == "D"


def _race(terms=True):
    return {
        "handicap": True,
        "runners": [{"name": f"H{i}", "win_odds": o} for i, o in enumerate(ODDS)],
        "terms": [{"bookmaker": "Book A", "places": 5, "fraction": "1/5"}] if terms else [],
    }


def test_price_race_end_to_end():
    out = price_race(_race())
    assert out["field_size"] == 12 and out["standard_terms"] == {"places": 3, "fraction": 0.25}
    assert len(out["runners"]) == 12
    assert sum(r["win_probability"] for r in out["runners"]) == pytest.approx(1.0)
    r = out["runners"][0]
    assert len(r["positions"]) == 9
    assert r["top3_probability"] <= r["top4_probability"] <= r["top5_probability"] <= r["top6_probability"]
    assert out["opportunities"], "5 places at 1/5 in a 12-runner handicap should show some value"
    for o in out["opportunities"]:
        assert o["edge"] > 0 and o["each_way_ev"] > 0 and o["grade"] in "ABC"
        assert o["grade"] != "A"  # not calibrated yet
        assert o["p4"] > 0 and 0 <= o["confidence"] <= 100


def test_standard_terms_used_without_offers():
    out = price_race(_race(terms=False))
    assert out["offers"][0]["places"] == 3 and out["offers"][0]["fraction"] == 0.25


def test_non_runners_dropped():
    race = _race()
    race["runners"][0]["non_runner"] = True
    assert price_race(race)["field_size"] == 11


def test_fit_discounts_recovers_known_values():
    rng = np.random.default_rng(0)
    truth = (1.0, 0.7, 0.55, 0.5, 0.5, 0.5)
    races = []
    for i in range(300):
        p = market.devig_power(np.sort(rng.uniform(2, 40, size=10)))
        order = positions.simulate_orders(p, n_sims=1, discounts=truth, seed=i)[0]
        races.append({"p_win": p, "order": list(order)})
    fit = calibrate.fit_discounts(races)
    assert fit["fitted"] and fit["nll_fitted"] < fit["nll_prior"]
    assert abs(fit["discounts"][0] - 1.0) < 0.15
    assert abs(fit["discounts"][1] - 0.7) < 0.15
    report = calibrate.evaluate(races[:50], fit["discounts"], n_sims=1000)
    assert report["top3"]["n"] == 500 and 0 < report["top3"]["brier"] < 0.25


def test_fit_discounts_needs_enough_races():
    fit = calibrate.fit_discounts([{"p_win": [0.5, 0.5], "order": [0, 1]}])
    assert not fit["fitted"] and fit["discounts"] == list(positions.DEFAULT_DISCOUNTS)


CARD = {
    "timestamp": "2026-10-02T10:00:00Z",
    "races": [{
        "date": "2026-10-02", "time": "14:30", "course": "Testcourse", "handicap": True,
        "terms": [{"bookmaker": "Book A", "places": 5, "fraction": "1/5"}],
        "runners": [{"horse": f"Horse {i}", "number": i + 1, "jockey": "J One", "trainer": "T One",
                     "odds": {"Book A": o, "Book B": o * 0.95}} for i, o in enumerate(ODDS)],
        "result": ["Horse 2", "Horse 0", "Horse 5"],
    }],
}


def test_store_roundtrip_and_persist():
    assert store.import_card(CARD) == {"races": 1, "runners": 12, "results": 3}
    store.import_card(CARD)  # re-import: same race, new snapshot
    races = store.races_on("2026-10-02")
    assert len(races) == 1
    race = races[0]
    assert race["course"] == "Testcourse" and len(race["runners"]) == 12
    assert race["runners"][0]["odds"]["Book A"] == 3.5
    assert race["terms"] == [{"bookmaker": "Book A", "places": 5, "fraction": 0.2}]
    priced = price_race(race)
    store.save_priced(priced)
    hist = store.races_with_results()
    assert hist[0]["order"][:3] == [2, 0, 5]
    store.save_calibration({"fitted": False, "discounts": [1.0, 0.8]})
    assert store.latest_calibration()["discounts"] == [1.0, 0.8]


def test_api_endpoints(monkeypatch):
    monkeypatch.setattr(app_module, "require_pro", lambda a: "u_test")
    store.import_card(CARD)
    with TestClient(app_module.app) as client:
        r = client.get("/stables/races?date=2026-10-02")
        assert r.status_code == 200
        body = r.json()
        assert body["races"][0]["course"] == "Testcourse"
        assert all(o["course"] == "Testcourse" for o in body["opportunities"])
        assert client.get("/stables/races?date=nope").status_code == 400
        r = client.post("/stables/price", json={
            "handicap": True,
            "runners": [{"name": f"R{i}", "odds": o} for i, o in enumerate(ODDS)],
            "terms": [{"bookmaker": "Book A", "places": 5, "fraction": "1/5"}],
        })
        assert r.status_code == 200 and len(r.json()["runners"]) == 12
        assert client.post("/stables/price", json={"runners": [{"name": "x", "odds": 2}]}).status_code == 422
