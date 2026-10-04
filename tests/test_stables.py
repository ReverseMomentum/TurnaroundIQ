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


# ---- free checks: Kaggle readers, paper backtest, Betfair BSP -------------

import sqlite3  # noqa: E402

from racing import backtest, datasets  # noqa: E402


def _synthetic(n_races=60, seed=0):
    rng = np.random.default_rng(seed)
    rows_r, rows_h = [], []
    for rid in range(n_races):
        odds = np.sort(rng.uniform(2, 30, size=10))
        p = market.devig_power(odds)
        order = positions.simulate_orders(p, n_sims=1, seed=rid)[0]
        pos = np.empty(10, int)
        pos[order] = np.arange(1, 11)
        rows_r.append({"rid": rid, "date": f"2019-0{1 + rid % 9}-1{rid % 9} 14:30:00", "course": "Testford",
                       "title": "Test Handicap" if rid % 2 else "Test Stakes", "countryCode": "GB"})
        for i in range(10):
            rows_h.append({"rid": rid, "horseName": f"H{rid}-{i}", "decimalPrice": 1 / odds[i],
                           "position": 40 if (i == 9 and pos[i] == 10) else int(pos[i])})
    return rows_r, rows_h


def test_parsers():
    assert datasets.parse_sp("9/2F") == 5.5 and datasets.parse_sp("Evens") == 2.0
    assert datasets.parse_sp("11/10JF") == pytest.approx(2.1) and datasets.parse_sp("") is None
    assert datasets.parse_pos("3=") == 3 and datasets.parse_pos("PU") is None and datasets.parse_pos(40) is None


def test_hwaitt_reader_and_backtest(tmp_path):
    import pandas as pd

    r, h = _synthetic()
    pd.DataFrame(r).to_csv(tmp_path / "races_2019.csv", index=False)
    pd.DataFrame(h).to_csv(tmp_path / "horses_2019.csv", index=False)
    assert "horse    -> horseName" in datasets.peek([tmp_path])
    races = datasets.load_races([tmp_path], years=(2019, 2019))
    assert len(races) == 60
    race = races[0]
    assert len(race["runners"]) == 10 and race["runners"][0]["odds"] > 1
    assert race["finish"][race["order"][0]] == 1
    assert sum(r["handicap"] for r in races) == 30
    assert datasets.load_races([tmp_path], years=(2020, 2021)) == []
    bt = backtest.ew_backtest(races, None, extra=1, n_sims=500)
    assert bt["races"] == 60
    assert bt["all"]["bets"] > 0 and bt["all"]["roi"] >= -1
    assert sum(g["bets"] for g in bt["by_grade"].values()) == bt["all"]["bets"]


def test_rpscrape_sqlite_reader(tmp_path):
    con = sqlite3.connect(tmp_path / "results.db")
    con.execute("CREATE TABLE data (date TEXT, region TEXT, course TEXT, off TEXT, race_name TEXT, "
                "horse TEXT, pos TEXT, sp TEXT)")
    sps = ["2/1F", "3/1", "5/1", "8/1", "12/1", "20/1"]
    for race in range(3):
        for i, sp in enumerate(sps):
            con.execute("INSERT INTO data VALUES (?,?,?,?,?,?,?,?)",
                        ("2025-05-0%d" % (race + 1), "GB", "Testford", "2:30", "Novice Hurdle",
                         f"R{race}-{i}", "PU" if i == 5 else str(i + 1), sp))
    con.execute("INSERT INTO data VALUES ('2025-05-01','FR','Paris','3:00','Prix','X','1','2/1')")
    con.commit()
    con.close()
    races = datasets.load_races([tmp_path])
    assert len(races) == 3
    assert races[0]["runners"][0]["odds"] == 3.0 and races[0]["finish"][5] is None
    assert races[0]["order"] == [0, 1, 2, 3, 4]


def _bsp_csv(rows):
    head = "EVENT_ID,MENU_HINT,EVENT_NAME,EVENT_DT,SELECTION_ID,SELECTION_NAME,WIN_LOSE,BSP\n"
    return head + "\n".join(",".join(map(str, r)) for r in rows)


def test_bsp_join_and_check():
    bsps = [3.0, 4.0, 6.0, 9.0, 13.0, 21.0, 34.0, 51.0]
    win = _bsp_csv([(1, "Testford 2nd Oct", "2m Hcap", "02-10-2026 14:30", 100 + i, f"H{i}",
                     int(i == 1), b) for i, b in enumerate(bsps)])
    place = _bsp_csv([(2, "Testford 2nd Oct", "4 TBP", "02-10-2026 14:30", 100 + i, f"H{i}",
                       int(i in (0, 1, 4, 6)), round(1 + (b - 1) / 4, 2)) for i, b in enumerate(bsps)])
    races = backtest.bsp_races(win, place)
    assert len(races) == 1 and races[0]["places"] == 4 and sum(races[0]["p_win"]) == pytest.approx(1)
    rep = backtest.bsp_check(races * 5, {"prior": positions.DEFAULT_DISCOUNTS, "harville": [1.0]}, n_sims=500)
    assert set(rep["top4"]) == {"prior", "harville", "place_market_bsp"}
    assert rep["top4"]["prior"]["n"] == 40 and rep["top4"]["prior"]["observed_rate"] == 0.5


def test_date_and_price_detection(tmp_path):
    import pandas as pd

    d = datasets.parse_dates(pd.Series(["90/01/01 12:30", "90/12/31 14:00"]))
    assert [x.year for x in d] == [1990, 1990] and d.iloc[1].month == 12
    assert datasets.odds_from_price_column(pd.Series([0.2, 0.5])).tolist() == [5.0, 2.0]
    assert datasets.odds_from_price_column(pd.Series([50.0, 6.0])).tolist() == [50.0, 6.0]
    # forward.csv-style file (no results) is skipped by peek and load
    pd.DataFrame([{"course": "X", "marketTime": "2020-09-11", "horseName": "A", "decimalPrice": 5.0}]
                 ).to_csv(tmp_path / "forward.csv", index=False)
    r, h = _synthetic(n_races=6)
    pd.DataFrame(r).to_csv(tmp_path / "races_2019.csv", index=False)
    pd.DataFrame(h).to_csv(tmp_path / "horses_2019.csv", index=False)
    out = datasets.peek([tmp_path])
    assert "pos      -> position" in out and "dates:" in out
    assert len(datasets.load_races([tmp_path])) == 6


def test_non_finishers_never_place_and_others_move_up():
    from racing import nonfinish

    p = np.array([0.4, 0.3, 0.2, 0.1])
    sim = positions.simulate(p, 20_000, dnf=[0.5, 0, 0, 0])
    assert sim["P"][0].sum() == pytest.approx(0.5, abs=0.02)
    assert sim["P"][1:].sum(axis=1) == pytest.approx(np.ones(3))
    base = positions.simulate(p, 20_000)
    assert sim["top"][1, 1] > base["top"][1, 1]
    assert nonfinish.race_type("2m Handicap Chase") == "chase"
    assert nonfinish.race_type("Novices' Hurdle") == "hurdle" and nonfinish.race_type("Maiden Stakes") == "flat"
    rates = nonfinish.rates_for([3.0, 15.0, 100.0], "chase")
    assert rates[0] < rates[1] < rates[2]


def test_jumps_race_lowers_place_chances():
    race = _race()
    flat = price_race(race)
    chase = price_race({**race, "race_type": "chase"})
    assert chase["runners"][-1]["top5_probability"] < flat["runners"][-1]["top5_probability"]


def test_fit_rates_and_finishers_only_fit():
    from racing import nonfinish

    races = [{"race_type": "chase", "runners": [{"odds": 3.0}, {"odds": 30.0}],
              "finish": [1, None]}] * 400
    t = nonfinish.fit_rates(races)
    assert t["chase"][0] == 0.0 and t["chase"][3] == 1.0
    assert t["hurdle"] == nonfinish.DEFAULT_RATES["hurdle"]
    logp, order = calibrate._finishers_only({"p_win": [0.5, 0.3, 0.2], "order": [2, 0]})
    assert len(logp) == 2 and order == [1, 0]


def test_shrink_and_backtest_summary():
    from racing.extra_place import shrink

    ev = evaluate(0.10, [0.1, 0.2, 0.3, 0.38, 0.45], 11.0, Terms("B", 5, 0.2, 3))
    half = shrink(ev, 0.5)
    assert half["raw_model_probability"] == pytest.approx(0.45)
    assert half["model_probability"] == pytest.approx(1 / 3 + 0.5 * (0.45 - 1 / 3))
    assert half["each_way_ev"] < ev["each_way_ev"] and half["win_ev"] == ev["win_ev"]
    out = price_race(_race(), {"edge_shrink": 0.0})
    assert all(o["edge"] == pytest.approx(0) for o in out["opportunities"])
    # synthetic bets where the model is twice as optimistic as reality
    bets = [{"p_place": 0.5, "market_place": 0.3, "place_odds": 3.4, "win_ev": 0.0, "grade": "B",
             "ev": 0.35, "win_odds": 13.0, "return": 0.5 + 0.5 * 3.4 * (i % 10 < 4), "placed": i % 10 < 4,
             "extra_hit": False, "race_type": "flat"} for i in range(1000)]
    fit = backtest.fit_shrink(bets)
    assert fit["fitted"] and 0.4 <= fit["edge_shrink"] <= 0.6
    summ = backtest.summarise(bets)
    assert summ["all"]["bets"] == 1000 and summ["by_grade"]["B"]["roi"] == pytest.approx(0.5 + 0.4 * 1.7 - 1)


def test_refresh_reprices_but_respects_cooldown(monkeypatch):
    from api import stables as stables_api

    monkeypatch.setattr(app_module, "require_pro", lambda a: "u_test")
    store.import_card(CARD)
    calls = []
    real = stables_api.price_race
    monkeypatch.setattr(stables_api, "price_race", lambda r, cal: calls.append(1) or real(r, cal, n_sims=500))
    stables_api._cache.clear()
    with TestClient(app_module.app) as client:
        first = client.get("/stables/races?date=2026-10-02").json()
        assert first["priced_at"] and len(calls) == 1
        client.get("/stables/races?date=2026-10-02")                 # cached
        client.get("/stables/races?date=2026-10-02&refresh=true")    # inside cooldown: cached
        assert len(calls) == 1
        stables_api._cache["2026-10-02"] = (0.0, first)              # pricing is old
        client.get("/stables/races?date=2026-10-02&refresh=true")
        assert len(calls) == 2


# ---- Betfair collector (fake HTTP) and value-from prices ------------------

class _Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self._body


class _FakeBetfair:
    def __init__(self, n=10, start="2026-10-04T13:30:00Z"):
        self.calls, self.n, self.start = [], n, start

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        self.calls.append(url if json is None else json["method"].split("/")[-1])
        if "login" in url:
            return _Resp({"token": "tok", "status": "SUCCESS"})
        method = json["method"].split("/")[-1]
        if method == "listMarketCatalogue":
            return _Resp({"result": [{
                "marketId": "1.234", "marketName": "2m4f Hcap Chs", "marketStartTime": self.start,
                "event": {"venue": "Testford", "countryCode": "GB"},
                "description": {"raceType": "Chase"},
                "runners": [{"selectionId": 100 + i, "runnerName": f"Horse {i}",
                             "metadata": {"CLOTH_NUMBER": str(i + 1), "JOCKEY_NAME": "J Doe", "AGE": "7"}}
                            for i in range(self.n)]}]})
        if method == "listMarketBook":
            odds = [3.5, 4.5, 6, 8, 10, 12, 15, 20, 25, 33, 40, 50][: self.n]
            return _Resp({"result": [{"marketId": "1.234", "runners": [
                {"selectionId": 100 + i, "status": "REMOVED" if i == self.n - 1 else "ACTIVE",
                 "totalMatched": 1000.0,
                 "ex": {"availableToBack": [{"price": o}], "availableToLay": [{"price": round(o * 1.05, 2)}]}}
                for i, o in enumerate(odds)]}]})
        return _Resp({"error": {"code": "?"}})


def test_betfair_collect_into_store(monkeypatch, tmp_path):
    from collectors import betfair

    for k, v in {"BETFAIR_APP_KEY": "k", "BETFAIR_USERNAME": "u", "BETFAIR_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(betfair, "SESSION_FILE", tmp_path / "s.json")
    fake = _FakeBetfair(n=12)
    out = betfair.collect(12, betfair.Client(http=fake))
    assert out["races"] == 1 and out["runners"] == 12
    assert fake.calls[0].endswith("/api/login") and "listMarketBook" in fake.calls
    race = store.races_on("2026-10-04")[-1]
    assert race["course"] == "Testford" and race["time"] == "14:30"    # UK time (BST)
    assert race["race_type"] == "chase" and race["handicap"] is True
    assert sum(r["non_runner"] for r in race["runners"]) == 1
    assert race["runners"][0]["exchange"]["back"] == 3.5
    priced = price_race(race)
    assert priced["probability_source"] == "exchange" and priced["field_size"] == 11
    vf = priced["runners"][-1]["value_from"]
    assert set(vf) == {"0", "1", "2", "3"}
    # more places paid -> a shorter price is already value
    assert vf["3"] is None or vf["0"] is None or vf["3"] <= vf["0"]
    # session token is reused on the next run
    fake2 = _FakeBetfair(n=12)
    betfair.collect(12, betfair.Client(http=fake2))
    assert not any(str(c).endswith("/api/login") for c in fake2.calls)


def test_betfair_login_refused_is_reported(monkeypatch, tmp_path):
    from collectors import betfair

    for k, v in {"BETFAIR_APP_KEY": "k", "BETFAIR_USERNAME": "u", "BETFAIR_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(betfair, "SESSION_FILE", tmp_path / "s.json")

    class Refuse(_FakeBetfair):
        def post(self, url, **kw):
            return _Resp({"status": "FAIL", "error": "INVALID_USERNAME_OR_PASSWORD"})
    with pytest.raises(betfair.BetfairError, match="INVALID_USERNAME_OR_PASSWORD"):
        betfair.Client(http=Refuse()).login(force=True)
    monkeypatch.delenv("BETFAIR_APP_KEY")
    assert not betfair.configured()


def test_min_value_odds():
    from racing.extra_place import min_value_odds

    o = min_value_odds(0.06, 0.40, 0.2)
    po = 1 + (o - 1) * 0.2
    assert 0.5 * (0.06 * o - 1) + 0.5 * (0.40 * po - 1) == pytest.approx(0.04, abs=1e-3)
    assert min_value_odds(0.06, 0.40, 0.2, edge_shrink=0.5) > o
    assert min_value_odds(0.06, 0.45, 0.2) < o
    assert min_value_odds(0.0, 0.0, 0.2) is None
    assert min_value_odds(0.06, 0.40, 0.0) is None


def test_prune_keeps_last_snapshot():
    store.import_card({**CARD, "timestamp": "2020-01-01T10:00:00+00:00",
                       "races": [{**CARD["races"][0], "runners": [
                           {**r, "exchange": {"back": 5.0, "lay": 5.2}} for r in CARD["races"][0]["runners"]]}]})
    store.import_card({**CARD, "timestamp": "2020-01-01T11:00:00+00:00",
                       "races": [{**CARD["races"][0], "runners": [
                           {**r, "exchange": {"back": 6.0, "lay": 6.2}} for r in CARD["races"][0]["runners"]]}]})
    assert store.prune_snapshots() >= 12
    race = store.races_on("2026-10-02")[0]
    assert race["runners"][0]["exchange"]["back"] == 6.0
    assert store.last_snapshot() is not None
