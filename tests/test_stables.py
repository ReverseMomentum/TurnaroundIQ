"""The Stables: extra-place value model (racing/)."""

import numpy as np
import time

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
    assert race["terms"] == [{"bookmaker": "Book A", "places": 5, "fraction": 0.2, "min_runners": None}]
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
        again = client.get("/stables/races?date=2026-10-02&refresh=true").json()
        assert again["priced_at"] == first["priced_at"]              # answered at once from the cache
        for _ in range(100):                                          # re-priced in the background
            if not stables_api._busy:
                break
            time.sleep(0.05)
        assert len(calls) == 2
        assert client.get("/stables/races?date=2026-10-02").json()["refreshing"] is False


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
    vf = next(r for r in reversed(priced["runners"]) if not r["beyond_value_range"])["value_from"]
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


def test_betfair_proxy_setting(monkeypatch):
    from collectors import betfair

    monkeypatch.setenv("BETFAIR_PROXY", "socks5h://127.0.0.1:1080")
    c = betfair.Client()
    assert c.http.proxies["https"] == "socks5h://127.0.0.1:1080"
    assert c.http.headers["User-Agent"].startswith("TurnaroundIQ")
    monkeypatch.delenv("BETFAIR_PROXY")
    assert not betfair.Client().http.proxies


def test_recalibration_corrects_a_longshot_bias():
    from racing import recalibrate

    rng = np.random.default_rng(4)

    def races(n_races, seed0):
        out = []
        for j in range(n_races):
            odds = np.round(np.sort(rng.uniform(2, 80, size=10)), 2)
            p = market.devig_power(odds)
            truth = p ** 1.4 / (p ** 1.4).sum()   # outsiders really do worse than SP says
            order = positions.simulate_orders(truth, n_sims=1, seed=seed0 + j)[0]
            finish = [0] * 10
            for pos, i in enumerate(order):
                finish[i] = pos + 1
            out.append({"key": str(seed0 + j), "handicap": True, "race_type": "flat", "finish": finish,
                        "runners": [{"name": str(i), "odds": float(o)} for i, o in enumerate(odds)]})
        return out

    train, test = races(600, 0), races(300, 10_000)
    recal = recalibrate.fit(recalibrate.build_rows(train, n_sims=500))
    assert recal["fitted"] and recal["win"][1] > 1.1          # sharpens toward favourites
    rep = recalibrate.report(recalibrate.build_rows(test, n_sims=500), recal)
    big = rep.get("51+") or rep["34-51"]
    assert abs(big["calibrated"] - big["actual"]) < abs(big["raw"] - big["actual"])
    p_c, top_c = recalibrate.apply(np.array([0.5, 0.3, 0.2]), np.array([[.5, .8, 1], [.3, .7, 1], [.2, .5, 1]]), recal)
    assert p_c.sum() == pytest.approx(1) and np.all(np.diff(top_c, axis=1) >= 0)
    out = price_race(_race(), {"recal": recal})
    assert out["recalibrated"] and out["runners"][0]["value_from"]


def test_no_value_calls_from_33_1_and_win_stage_fixed():
    race = {"handicap": True, "terms": [{"bookmaker": "B", "places": 6, "fraction": "1/4"}],
            "runners": [{"name": f"H{i}", "win_odds": o} for i, o in enumerate(ODDS + [67.0, 101.0])]}
    out = price_race(race)
    longshots = [r for r in out["runners"] if r["best_win_odds"] >= 34]
    assert longshots and all(r["value_from"] == {} and r["beyond_value_range"] for r in longshots)
    assert all(v is None or v < 34 for r in out["runners"] for v in r["value_from"].values())
    assert all(o["grade"] == "C" for o in out["opportunities"] if o["win_odds"] >= 34)
    assert all(o["grade"] == "C" for o in out["opportunities"] if o["win_odds"] > 51)
    rng = np.random.default_rng(1)
    races = []
    for i in range(250):
        p = market.devig_power(np.sort(rng.uniform(2, 40, size=8)))
        races.append({"p_win": p, "order": list(positions.simulate_orders(p, 1, seed=i)[0])})
    assert calibrate.fit_discounts(races)["discounts"][0] == 1.0
    assert calibrate.fit_discounts(races, fix_first=False)["discounts"][0] != 1.0


def test_started_races_are_marked_and_dropped_from_opportunities():
    from datetime import datetime
    from api import stables as stables_api

    now = datetime(2026, 10, 4, 15, 0, tzinfo=stables_api.UK)
    assert stables_api._started({"date": "2026-10-04", "time": "14:59"}, now)
    assert stables_api._started({"date": "2026-10-04", "time": "15:00"}, now)
    assert not stables_api._started({"date": "2026-10-04", "time": "15:01"}, now)
    assert stables_api._started({"date": "2026-10-03", "time": "21:00"}, now)
    assert not stables_api._started({"date": "2026-10-05", "time": "12:00"}, now)
    body = {"races": [{"race_id": 1, "date": "2000-01-01", "time": "12:00"},
                      {"race_id": 2, "date": "2099-01-01", "time": "12:00"}],
            "opportunities": [{"race_id": 1}, {"race_id": 2}]}
    out = stables_api._with_live_status(body)
    assert [r["started"] for r in out["races"]] == [True, False]
    assert out["opportunities"] == [{"race_id": 2}] and out["started_count"] == 1


def test_offers_admin_only_and_priced(monkeypatch):
    from api import stables as stables_api

    store.import_card(CARD)
    race_id = store.races_on("2026-10-02")[0]["race_id"]
    monkeypatch.setattr(app_module, "require_pro", lambda a: a.replace("Bearer ", ""))
    monkeypatch.setattr(app_module, "ADMIN_USER_IDS", {"u_admin"})
    body = {"bookmaker": "Book Z", "places": 6, "fraction": "1/5", "race_ids": [race_id, 999999]}
    with TestClient(app_module.app) as client:
        assert client.post("/stables/offers", json=body, headers={"Authorization": "Bearer u_user"}).status_code == 403
        r = client.post("/stables/offers", json=body, headers={"Authorization": "Bearer u_admin"})
        assert r.status_code == 200 and r.json()["updated"] == 1          # unknown race id skipped
        bad = {**body, "fraction": "five"}
        assert client.post("/stables/offers", json=bad, headers={"Authorization": "Bearer u_admin"}).status_code == 400
        races = client.get("/stables/races?date=2026-10-02", headers={"Authorization": "Bearer u_user"}).json()
        assert races["can_edit_offers"] is False
        race = next(x for x in races["races"] if x["race_id"] == race_id)
        assert {"bookmaker": "Book Z", "places": 6} .items() <= next(
            t for t in race["offers"] if t["bookmaker"] == "Book Z").items()
        vf = [r["offer_value_from"].get("Book Z") for r in race["runners"]]
        assert "Book Z" in race["runners"][0]["offer_value_from"]
        # 6 places at 1/5 needs a shorter price than 3 places at 1/5 (the generic "+0")
        pairs = [(r["offer_value_from"]["Book Z"], r["value_from"].get("0")) for r in race["runners"]
                 if r["offer_value_from"].get("Book Z") and r["value_from"].get("0")]
        assert pairs and all(a <= b for a, b in pairs)
        assert client.get("/stables/races?date=2026-10-02", headers={"Authorization": "Bearer u_admin"}).json()["can_edit_offers"]
        d = client.delete(f"/stables/offers?race_id={race_id}&bookmaker=Book%20Z", headers={"Authorization": "Bearer u_admin"})
        assert d.json()["deleted"] == 1
    assert all(t["bookmaker"] != "Book Z" for t in store.races_on("2026-10-02")[0]["terms"])


# ---- tracking bets, results, auto-settle, tracker -------------------------

def test_each_way_profit_maths():
    from api.tracked import ew_returns, ew_expected

    # £10 EW total at 11.0, 1/5: place odds 3.0
    assert ew_returns("won", 10, 11, 0.2) == pytest.approx(5 * 10 + 5 * 2)
    assert ew_returns("placed", 10, 11, 0.2) == pytest.approx(-5 + 5 * 2)
    assert ew_returns("lost", 10, 11, 0.2) == -10
    assert ew_returns("void", 10, 11, 0.2) == 0
    assert ew_expected(10, 11, 0.2, 0.1, 0.45) == pytest.approx(5 * (1.1 - 1) + 5 * (0.45 * 3 - 1))
    assert store.ew_result(True, None, None, 5) == "won"
    assert store.ew_result(False, 3, None, 5) == "placed"
    assert store.ew_result(False, None, 5, 5) == "lost"
    assert store.ew_result(False, None, 3, 5) is None        # outside top 3 but top 5 unknown
    assert store.ew_result(False, 4, 3, 5) == "placed"


def test_track_settle_and_report(monkeypatch):
    from racing import bets as racing_bets

    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.9", "date": "2026-10-04"}]})
    race = next(r for r in store.races_on("2026-10-04") if r["course"] == "Testcourse")
    with pytest.raises(racing_bets.TrackError):
        racing_bets.track("u_t", race["race_id"], "Nope", "Book Z", 10, 10, 5, "1/5")
    bet = racing_bets.track("u_t", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5")
    assert bet["product"] == "stables" and bet["status"] == "open" and bet["ew_places"] == 5
    snap = bet["snapshot"]
    assert snap["offer"]["places_paid"] == 5 and snap["offer"]["win_odds"] == 16.0
    assert snap["runner"]["jockey"] == "J One" and snap["race"]["course"] == "Testcourse"
    assert bet["expected_profit"] is not None
    # results: Horse 6 placed in a 4-place market -> placed for a 5-place bet
    hid = {r["name"]: r["horse_id"] for r in race["runners"]}
    store.save_results(race["race_id"], [
        {"horse_id": hid["Horse 0"], "won": True, "exchange_sp": 4.0, "placed_within": 3},
        {"horse_id": hid["Horse 6"], "won": False, "exchange_sp": 14.0, "placed_within": 4, "outside_within": 3}])
    assert racing_bets.auto_settle() >= 1
    settled = next(b for b in tracked_store_list("u_t") if b["id"] == bet["id"])
    assert settled["result"] == "placed" and settled["actual_profit"] == pytest.approx(-5 + 5 * 3.0)
    rep = racing_bets.report("u_t")
    assert rep["all"]["settled"] >= 1 and rep["all"]["avg_clv"] is None     # not every runner has an SP yet
    assert "Book Z" in rep["by_bookmaker"]
    # every runner's SP known: CLV = the bet's each-way EV at the chances SP gave the race
    store.save_results(race["race_id"], [{"horse_id": hid[n], "exchange_sp": o} for n, o in
                                         zip([f"Horse {i}" for i in range(len(ODDS))], ODDS) if n not in ("Horse 0", "Horse 6")])
    clv = racing_bets.report("u_t")["all"]["avg_clv"]
    sps = store.race_sps(race["race_id"])
    p6 = (1 / sps[hid["Horse 6"]]) / sum(1 / v for v in sps.values())
    assert clv is not None and -0.6 < clv < 0.6
    assert clv > 0.5 * (p6 * 16 - 1) - 0.01      # at least the win half; the place half is the extra-place edge


def tracked_store_list(uid):
    from api import tracked

    return tracked.list_tracked(uid, limit=100)


def test_betfair_results_collection(monkeypatch, tmp_path):
    # today (UK) at 00:01: always gone off and inside the 36-hour results window
    _DAY = __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("Europe/London")).date().isoformat()
    from collectors import betfair

    for k, v in {"BETFAIR_APP_KEY": "k", "BETFAIR_USERNAME": "u", "BETFAIR_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(betfair, "SESSION_FILE", tmp_path / "s.json")
    store.import_card({"timestamp": f"{_DAY}T00:00:00Z", "races": [{
        "id": "bf:1.777", "date": _DAY, "time": "00:01", "course": "Resultford", "handicap": True,
        "runners": [{"horse": f"R{i}", "exchange": {"back": o, "lay": o + 0.1}} for i, o in enumerate([3, 5, 8, 12, 20, 30])]}]})

    class Fake(_FakeBetfair):
        def post(self, url, data=None, json=None, headers=None, timeout=None):
            if "login" in url:
                return _Resp({"token": "t", "status": "SUCCESS"})
            m, prm = json["method"].split("/")[-1], json["params"]
            if m == "listMarketCatalogue" and "marketIds" in prm["filter"]:
                return _Resp({"result": [{"marketId": "1.777", "marketStartTime": f"{_DAY}T00:01:00Z",
                                          "event": {"id": "E1"},
                                          "runners": [{"selectionId": 10 + i, "runnerName": f"R{i}"} for i in range(6)]}]})
            if m == "listMarketCatalogue":
                return _Resp({"result": [
                    {"marketId": "1.778", "marketStartTime": f"{_DAY}T00:01:00Z", "event": {"id": "E1"},
                     "description": {"numberOfWinners": 3}},
                    {"marketId": "1.779", "marketStartTime": f"{_DAY}T00:01:00Z", "event": {"id": "E1"},
                     "description": {"numberOfWinners": 4}}]})
            if m == "listMarketBook" and "1.777" in prm["marketIds"]:
                return _Resp({"result": [{"marketId": "1.777", "status": "CLOSED", "runners": [
                    {"selectionId": 10 + i, "status": "WINNER" if i == 1 else "LOSER", "sp": {"actualSP": 3.0 + i}}
                    for i in range(6)]}]})
            if m == "listMarketBook":
                return _Resp({"result": [
                    {"marketId": "1.778", "status": "CLOSED", "runners": [
                        {"selectionId": 10 + i, "status": "WINNER" if i in (0, 1, 2) else "LOSER"} for i in range(6)]},
                    {"marketId": "1.779", "status": "CLOSED", "runners": [
                        {"selectionId": 10 + i, "status": "WINNER" if i in (0, 1, 2, 4) else "LOSER"} for i in range(6)]}]})
            return _Resp({"error": {"code": "?"}})

    out = betfair.collect_results(betfair.Client(http=Fake()), hours=48)
    assert out["result_races"] == 1
    conn = __import__("database").get_db()
    rows = dict(conn.execute(
        "SELECT h.name, COALESCE(x.finish_position, '') || '|' || COALESCE(x.placed_within,'') || '|' || COALESCE(x.outside_within,'') "
        "|| '|' || x.exchange_sp FROM rac_results x JOIN rac_horses h ON h.id = x.horse_id "
        "JOIN rac_races r ON r.id = x.race_id WHERE r.external_id = 'bf:1.777'").fetchall())
    conn.close()
    assert rows["R1"].startswith("1|3|")
    assert "R4" in rows and rows["R4"].split("|")[1:3] == ["4", "3"]
    assert betfair.collect_results(betfair.Client(http=Fake()), hours=48)["result_races"] == 0  # done once


def test_comma_separated_bookmakers(monkeypatch):
    from api import stables as stables_api

    assert stables_api.split_bookmakers(" Bet365, Paddy Power ,bet365,, ") == ["Bet365", "Paddy Power"]
    store.import_card(CARD)
    race_id = store.races_on("2026-10-02")[0]["race_id"]
    monkeypatch.setattr(app_module, "require_pro", lambda a: "u_admin")
    monkeypatch.setattr(app_module, "ADMIN_USER_IDS", {"u_admin"})
    with TestClient(app_module.app) as client:
        r = client.post("/stables/offers", json={"bookmaker": "Book P, Book Q", "places": 5, "fraction": "1/5",
                                                 "race_ids": [race_id]})
        assert r.json() == {"updated": 2, "bookmakers": ["Book P", "Book Q"], "races": 1}
        assert client.post("/stables/offers", json={"bookmaker": " , ", "places": 5, "race_ids": [race_id]}).status_code == 400
    books = {t["bookmaker"] for t in store.races_on("2026-10-02")[0]["terms"]}
    assert {"Book P", "Book Q"} <= books


# ---- learned model: features, live features, engine --------------------------

def test_name_keys_and_parsers():
    from racing import features as F
    from racing import live_features as L

    assert L.horse_key("Galopin Des Champs (FR)") == L.horse_key("Galopin des Champs")
    assert L.person_key("Willie Mullins") == L.person_key("W P Mullins") == "w mullins"
    assert L.person_key("J Smith (3)") == "j smith"
    assert L.distance_from_name("2m4f Hcap Chs") == 20 and L.distance_from_name("7f Mdn Stks") == 7
    assert L.distance_from_name("1m Hcap") == 8 and L.distance_from_name("Hcap") is None
    assert L.weight_lbs("9-7") == 133 and L.weight_lbs("140") == 140
    assert F.parse_form("1-3P20/4") == [1, 3, 12, 2, 10, 4]
    assert F.form_features([3, 1, 5])["avg3_pos"] == 3.0
    assert F.furlongs("2m4f") == 20 and F.furlongs(1609) == 8


def test_live_features_from_history_and_learned_engine():
    from racing import learn, live_features

    store.import_card({"timestamp": "2026-10-04T09:00:00Z", "races": [{
        "id": "bf:5.555", "date": "2026-10-05", "time": "14:00", "course": "Featureford",
        "name": "2m Hcap Hrd", "handicap": True, "race_type": "hurdle",
        "runners": [{"horse": f"F{i}", "jockey": "Paul Townend" if i == 0 else f"J{i}", "trainer": "W P Mullins",
                     "form": "1-21" if i == 0 else "0-9P", "official_rating": 120 - i, "weight": "11-0",
                     "days_since_run": 21, "exchange": {"back": o, "lay": o + 0.2}}
                    for i, o in enumerate([3, 5, 8, 12, 20, 30])]}]})
    store.add_history([{"race_ref": f"k:{i}", "date": "2025-01-0%d" % (i + 1), "course": "Featureford",
                        "dist_f": 16, "horse_key": "f0", "jockey_key": "p townend", "trainer_key": "w mullins",
                        "placed": 1, "source": "test"} for i in range(4)])
    rid = store.race_ids_for(["bf:5.555"])[0]
    assert live_features.refresh([rid]) == 6
    race = store.load_race(__import__("database").get_db(), rid)
    f0 = next(r for r in race["runners"] if r["name"] == "F0")["features"]
    f5 = next(r for r in race["runners"] if r["name"] == "F5")["features"]
    assert f0["course_rate"] > f5["course_rate"] and f0["horse_jockey_rate"] > 0.3
    assert f0["last_pos"] == 1 and f5["last_pos"] == 12 and f0["avg3_pos"] < f5["avg3_pos"]
    assert f0["or_rel"] > 0 > f5["or_rel"] and f0["log_days"] > 0
    blend = {"kind": "exploded", "fitted": True, "features": ["log_market_p", "course_rate"],
             "weights": [1.0, 0.8], "stats": {"mean": [0.3], "std": [0.1]}}
    plain = price_race(race)
    learned = price_race(race, {"blend": blend})
    w0 = lambda out: next(r for r in out["runners"] if r["name"] == "F0")["win_probability"]  # noqa: E731
    assert w0(learned) > w0(plain)
    assert "course_rate" in next(r for r in learned["runners"] if r["name"] == "F0")["features"]
    assert learn.apply([0.5, 0.5], [{}, {}], None).tolist() == [0.5, 0.5]


def test_training_features_ignore_unreadable_dates(tmp_path):
    import warnings
    import pandas as pd
    from racing import features as F

    races = [{"rid": i, "course": "A", "date": f"2016-01-{i + 1:02d} 14:00", "title": "Hcap", "metric": 1600,
              "condition": "Good", "countryCode": "GB"} for i in range(6)]
    races[3]["date"] = "not a date"
    horses = [{"rid": i, "horseName": f"H{k}", "decimalPrice": 0.2, "position": k + 1, "jockeyName": "J1",
               "trainerName": "T1", "weightSt": 9, "weightLb": 0, "OR": 70, "TR": 60, "saddle": k + 1}
              for i in range(6) for k in range(5)]
    pd.DataFrame(races).to_csv(tmp_path / "races_2016.csv", index=False)
    pd.DataFrame(horses).to_csv(tmp_path / "horses_2016.csv", index=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        out = F.training_features([tmp_path], (2016, 2016))
    assert len(out) == 25 and not any(k[0] == "3" for k in out)
    j30 = [f["jockey_30d"] for f in out.values()]
    assert all(v is not None and 0 < v < 1 for v in j30)
    assert F.shrink(0, -5, 10) == pytest.approx(0.3)


def test_odds_brackets():
    from racing.extra_place import ODDS_BANDS, odds_band

    assert len(ODDS_BANDS) == 9
    assert odds_band(2.5) == "1-3" and odds_band(3.0) == "3-5" and odds_band(11.0) == "8-12"
    assert odds_band(26.0) == "21-34" and odds_band(51.0) == "51+" and odds_band(400) == "51+"
    from racing import backtest
    out = backtest.summarise([{"grade": "B", "ev": 0.05, "win_odds": o, "return": 1.0, "placed": False,
                               "extra_hit": False, "race_type": "flat"} for o in (2.0, 13.0, 60.0)])
    assert list(out["by_odds"]) == ["1-3", "3-5", "5-8", "8-12", "12-16", "16-21", "21-34", "34-51", "51+"]
    assert out["by_odds"]["12-16"]["bets"] == 1


def test_harville_top3_matches_exact():
    p = np.array([0.35, 0.2, 0.15, 0.12, 0.08, 0.06, 0.04])
    exact = positions.exact_positions(p, [1.0])[:, :3].sum(1)
    assert np.allclose(positions.harville_top3(p), exact)
    assert positions.harville_top3([0.5, 0.3, 0.2]).tolist() == [1.0, 1.0, 1.0]


def test_placer_features_training_and_live(tmp_path):
    import pandas as pd
    from racing import features as F, live_features

    # "Plodder" is 20/1 every time and always finishes 3rd: places far more than its price says, never wins.
    races = [{"rid": i, "course": "A", "date": f"2016-02-{i + 1:02d}", "title": "Hcap Hurdle", "metric": 3200,
              "condition": "Soft", "countryCode": "GB"} for i in range(5)]
    prices = [2.5, 4.0, 6.0, 8.0, 12.0, 21.0]
    horses = [{"rid": i, "horseName": "Plodder" if k == 5 else f"H{i}{k}", "decimalPrice": 1 / prices[k],
               "position": 3 if k == 5 else (k + 1 if k < 2 else k + 2), "jockeyName": "J", "trainerName": "T",
               "weightSt": 10, "weightLb": 0, "OR": 100, "TR": 0, "saddle": k + 1}
              for i in range(5) for k in range(6)]
    pd.DataFrame(races).to_csv(tmp_path / "races_2016.csv", index=False)
    pd.DataFrame(horses).to_csv(tmp_path / "horses_2016.csv", index=False)
    out = F.training_features([tmp_path], (2016, 2016))
    first, last = out[("0", "Plodder")], out[("4", "Plodder")]
    assert first["place_excess"] == 0 and first["win_excess"] == 0      # no history yet
    assert last["place_excess"] > 0.3 and last["win_excess"] < 0         # placer, not a winner
    assert "placer" in F.GROUPS

    # live: the same numbers come from rac_history's stored chances
    h = [{"placed": 1, "won": 0, "exp_place": 0.2, "exp_win": 0.05} for _ in range(4)]
    f = live_features._placer(h + [{"placed": 1, "won": 0, "exp_place": None, "exp_win": None}])
    assert f["place_excess"] == pytest.approx(4 * 0.8 / (4 + F.SHRINK_HORSE))
    assert f["win_excess"] == pytest.approx(-4 * 0.05 / (4 + F.SHRINK_HORSE))
    assert live_features._placer([]) == {"place_excess": 0.0, "win_excess": 0.0, "priced_runs": 0}


def test_history_from_results_stores_expected_chances():
    from database import get_db
    from racing import live_features

    store.import_card({"timestamp": "2026-10-04T09:00:00Z", "races": [{
        "id": "bf:6.666", "date": "2026-10-04", "time": "13:00", "course": "Placeton", "name": "1m Hcap",
        "runners": [{"horse": f"P{i}", "exchange": {"back": o, "lay": o + 0.1}}
                    for i, o in enumerate([2.5, 4, 6, 9, 15])]}]})
    rid = store.race_ids_for(["bf:6.666"])[0]
    conn = get_db()
    hid = {r["name"]: r["horse_id"] for r in store.load_race(conn, rid)["runners"]}
    conn.execute("INSERT INTO rac_results (race_id, horse_id, finish_position, placed_within, outside_within) "
                 "VALUES (?,?,?,?,?)", (rid, hid["P4"], None, 3, None))
    conn.commit()
    conn.close()
    live_features.history_from_results([rid])
    conn = get_db()
    row = conn.execute("SELECT placed, exp_win, exp_place FROM rac_history WHERE race_ref = ? AND horse_key = 'p4'",
                       (f"live:{rid}",)).fetchone()
    conn.close()
    assert row[0] == 1 and 0 < row[1] < row[2] < 1


def test_segment_discounts_fit_and_fallback():
    from racing import backtest, learn

    rng = np.random.default_rng(1)
    races = []
    for i in range(500):     # big hurdle fields with a steep drop-off after the winner
        p = rng.dirichlet(np.ones(14) * 2)
        order = positions.simulate_orders(p, 1, [1.0, 0.45, 0.45, 0.45, 0.45, 0.45], seed=i)[0]
        races.append({"p_win": p, "order": list(order), "race_type": "hurdle"})
    for i in range(50):      # too few to get their own curve
        p = rng.dirichlet(np.ones(9) * 2)
        races.append({"p_win": p, "order": list(positions.simulate_orders(p, 1, None, seed=900 + i)[0]),
                      "race_type": "flat"})
    base = list(positions.DEFAULT_DISCOUNTS)
    seg = calibrate.fit_segment_discounts(races, base)
    assert set(seg["segments"]) == {"hurdle 12-15"} and seg["n_races"]["flat 8-11"] == 50
    d = seg["segments"]["hurdle 12-15"]
    assert d[0] == 1.0 and d[1] < 0.7                       # steeper than the 0.81 default
    cal = {"discounts": base, "segment_discounts": seg["segments"]}
    assert calibrate.discounts_for(cal, "hurdle", 13) == d
    assert calibrate.discounts_for(cal, "flat", 9) == base
    assert calibrate.discounts_for(None, "chase", 20) == list(positions.DEFAULT_DISCOUNTS)
    assert calibrate.segment("chase", 18) == "chase 16+" and calibrate.segment(None, 5) == "flat 2-7"

    # the engine and the ranking model pick the segment curve up
    runners = [{"name": f"R{i}", "win_odds": o} for i, o in enumerate([3, 5, 7, 9, 11, 13, 15, 17, 21, 26, 34, 41, 51])]
    out = price_race({"runners": runners, "race_type": "hurdle", "handicap": True}, cal, n_sims=2000)
    assert out["discounts"] == d and out["position_segment"] == "hurdle 12-15"
    assert price_race({"runners": runners[:9]}, cal, n_sims=2000)["position_segment"] is None
    ds = [{"runners": [{"odds": 1 / p} for p in r["p_win"]], "finish": [1] * len(r["p_win"]),
           "order": r["order"], "race_type": r["race_type"]} for r in races[:50] + races[-10:]]
    plain = learn.loss(ds, None, base)
    learn.tag_segments(ds, seg["segments"])
    assert ds[0]["discounts"] == d and "discounts" not in ds[-1]
    assert learn.loss(ds, None, base) < plain              # the steeper curve fits these races better
    learn.tag_segments(ds, None)
    assert "discounts" not in ds[0] and learn.loss(ds, None, base) == pytest.approx(plain)
    rows = backtest.to_calibration_races(ds[:3], segments=seg["segments"])
    assert rows[0]["discounts"] == d and rows[0]["race_type"] == "hurdle"


def test_vectorised_order_likelihood_matches_per_race():
    rng = np.random.default_rng(4)
    prepared = []
    for i in range(40):
        n = int(rng.integers(3, 14))
        p = rng.dirichlet(np.ones(n))
        order = list(positions.simulate_orders(p, 1, None, seed=i)[0])
        prepared.append(calibrate._finishers_only({"p_win": p, "order": order[:n - 2] if i % 4 == 0 else order}))
    lam = np.array([1.0, 0.8, 0.7, 0.6, 0.55, 0.5])
    slow = sum(calibrate._race_nll(lp, o, lam) for lp, o in prepared) / len(prepared)
    assert calibrate._nll_all(calibrate._pad(prepared), lam) == pytest.approx(slow)


def test_pasted_offer_list_parse_match_and_min_runners(monkeypatch):
    from racing import offers_text as T

    text = """Extra places today:
14:45 Killarney

(5 places, 1/5 odds)
Sky Bet (12+)
(4 places, 1/4 odds)
Betfred
16:05 Great Yarmouth
(4 places, 1/5 odds)
Sky Bet (8+)
21:00 Nowhere
(4 places, 1/5 odds)
bet365
"""
    offers, skipped = T.parse(text)
    assert [(o["bookmaker"], o["places"], o["fraction"], o["min_runners"]) for o in offers[:2]] == [
        ("Sky Bet", 5, "1/5", 12), ("Betfred", 4, "1/4", None)]
    assert offers[2]["course"] == "Great Yarmouth" and offers[2]["min_runners"] == 8
    pairs, missing = T.match(offers, [{"race_id": 1, "time": "14:45", "course": "Killarney"},
                                      {"race_id": 2, "time": "16:05", "course": "Yarmouth"}])
    assert [rid for rid, _ in pairs] == [1, 1, 2] and missing == ["21:00 Nowhere"]
    assert skipped == ["Extra places today:"]

    # end to end: stored, and a 12+ offer does not stand in a 10-runner race
    store.import_card({"timestamp": "2026-10-05T09:00:00Z", "races": [{
        "id": "bf:7.777", "date": "2026-10-05", "time": "14:45", "course": "Killarney", "name": "2m Hcap Hrd",
        "handicap": True, "runners": [{"horse": f"K{i}", "exchange": {"back": o, "lay": o + 0.2}}
                                      for i, o in enumerate([4, 5, 6, 8, 10, 12, 15, 20, 26, 34])]}]})
    monkeypatch.setattr(app_module, "require_pro", lambda a: "u_admin")
    monkeypatch.setattr(app_module, "ADMIN_USER_IDS", {"u_admin"})
    with TestClient(app_module.app) as client:
        out = client.post("/stables/offers/paste", json={"date": "2026-10-05", "text": text}).json()
        assert out["offers"] == 2 and out["races"] == 1
        assert "21:00 Nowhere" in out["not_found"] and "16:05 Great Yarmouth" in out["not_found"]
    race = next(r for r in store.races_on("2026-10-05") if r["course"] == "Killarney")
    assert {(t["bookmaker"], t["min_runners"]) for t in race["terms"]} == {("Sky Bet", 12), ("Betfred", None)}
    priced = price_race(race, n_sims=2000)
    assert [o["bookmaker"] for o in priced["offers"]] == ["Betfred"]
    assert priced["inactive_offers"] == [{"bookmaker": "Sky Bet", "places": 5, "fraction": 0.2, "min_runners": 12}]


def test_previous_runs_mean_matches_rolling_and_grade_by_price():
    import pandas as pd
    from racing import backtest, features as F

    rng = np.random.default_rng(0)
    df = pd.DataFrame({"horseName": rng.integers(0, 50, 800).astype(str),
                       "v": np.where(rng.random(800) < 0.3, np.nan, rng.random(800) * 10)})
    for k in (1, 3, 5):
        slow = df.groupby("horseName", sort=False)["v"].transform(lambda s: s.shift().rolling(k, min_periods=1).mean())
        assert np.allclose(slow.fillna(-1), F._prev_mean(df, "v", k).fillna(-1))
    bets = [{"grade": g, "ev": 0.1, "win_odds": o, "return": 1.0, "placed": False, "extra_hit": False,
             "race_type": "flat"} for g, o in (("A", 4.0), ("A", 40.0), ("B", 13.0))]
    cross = backtest.summarise(bets)["by_grade_odds"]
    assert cross["A"]["3-5"]["bets"] == 1 and cross["A"]["34-51"]["bets"] == 1 and cross["B"]["12-16"]["bets"] == 1


def test_each_way_with_win_lay_track_and_settle():
    from api.tracked import ew_expected, ew_lay_stake, ew_returns
    from racing import bets as racing_bets

    # £10 EW at 11.0, 1/5, full lay of the win half at 12.0, 2% commission
    ls, liab = ew_lay_stake(10, 11.0, 12.0, 2, 100)
    assert ls == pytest.approx(5 * 11 / 11.98, abs=0.01) and liab == pytest.approx(ls * 11, abs=0.02)
    assert ew_lay_stake(10, 11.0, 12.0, 2, 50)[0] == pytest.approx(ls / 2, abs=0.01)
    assert ew_lay_stake(10, 11.0, 12.0, 2, 0) == (None, None)
    won = ew_returns("won", 10, 11.0, 0.2, 12.0, ls, 2)
    placed = ew_returns("placed", 10, 11.0, 0.2, 12.0, ls, 2)
    lost = ew_returns("lost", 10, 11.0, 0.2, 12.0, ls, 2)
    # the win half is covered: winning vs placing differ by little; unplaced loses about the place half
    assert abs(won - placed) < 1.0 and lost == pytest.approx(-10 + ls * 0.98, abs=0.01) and placed > 0
    assert ew_returns("won", 10, 11.0, 0.2) == pytest.approx(5 * 10 + 5 * 2)   # no lay: unchanged
    e = ew_expected(10, 11.0, 0.2, 0.1, 0.45, 12.0, ls, 2)
    assert e == pytest.approx(0.1 * won + 0.35 * placed + 0.55 * lost, abs=0.02)

    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.10", "date": "2026-10-06"}]})
    race = next(r for r in store.races_on("2026-10-06") if r["course"] == "Testcourse")
    with pytest.raises(racing_bets.TrackError):     # a lay needs a usable lay price
        racing_bets.track("u_l", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5", lay_pct=100, lay_odds=1.0)
    bet = racing_bets.track("u_l", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5",
                            lay_pct=50, lay_odds=17.0, commission=2)
    assert bet["lay_stake"] == pytest.approx(0.5 * 5 * 16 / 16.98, abs=0.01) and bet["lay_odds"] == 17.0
    assert bet["snapshot"]["lay"]["pct"] == 50 and "win lay £" in bet["notes"]
    from api import tracked
    tracked.settle_tracked("u_l", bet["id"], "placed")
    s = next(b for b in tracked_store_list("u_l") if b["id"] == bet["id"])
    assert s["actual_profit"] == pytest.approx(-5 + 5 * 3.0 + bet["lay_stake"] * 0.98, abs=0.01)


def test_bsp_history_rows_and_live_counts():
    from database import get_db
    from racing import bsp_files, live_features

    assert bsp_files.course_from_menu("UK / Kemp 5th Oct") == "kemp"
    assert bsp_files.course_from_menu("Kempton (IRE) 12th Jan") == "kempton"
    assert live_features.same_course("kemp", "Kempton") and live_features.same_course("Epsm", "Epsom")
    assert live_features.same_course("Kempton (AW)", "kempton") and not live_features.same_course("kemp", "Kelso")
    bsps = [3.0, 4.0, 6.0, 9.0, 13.0, 21.0]
    win = _bsp_csv([(5, "UK / Kemp 1st Sep", "1m Hcap", "01-09-2025 14:30", 100 + i, f"Bsp Horse {i}",
                     int(i == 1), b) for i, b in enumerate(bsps)])
    place = _bsp_csv([(6, "UK / Kemp 1st Sep", "3 TBP", "01-09-2025 14:30", 100 + i, f"Bsp Horse {i}",
                       int(i in (1, 2, 5)), 1.5) for i in range(6)])
    rows = bsp_files.history_rows(win, place)
    by = {r["horse_key"]: r for r in rows}
    assert len(rows) == 6 and by["bsp horse 1"]["pos"] == 1 and by["bsp horse 5"]["placed"] == 1
    assert by["bsp horse 0"]["placed"] == 0 and by["bsp horse 0"]["dist_f"] == 8 and by["bsp horse 0"]["course"] == "kemp"
    assert 0 < by["bsp horse 5"]["exp_win"] < by["bsp horse 5"]["exp_place"] < 1
    assert abs(sum(r["exp_win"] for r in rows) - 1) < 1e-9
    # 4 places paid: an unplaced horse was not in the first three; a placed loser is unknown
    place4 = _bsp_csv([(6, "UK / Kemp 1st Sep", "4 TBP", "01-09-2025 14:30", 100 + i, f"Bsp Horse {i}",
                        int(i in (1, 2, 3, 5)), 1.5) for i in range(6)])
    by4 = {r["horse_key"]: r["placed"] for r in bsp_files.history_rows(win, place4)}
    assert by4["bsp horse 0"] == 0 and by4["bsp horse 5"] is None and by4["bsp horse 1"] == 1

    store.add_history(rows)
    store.import_card({"timestamp": "2026-10-04T09:00:00Z", "races": [{
        "id": "bf:8.888", "date": "2026-10-05", "time": "19:15", "course": "Kempton", "name": "1m Hcap",
        "runners": [{"horse": f"Bsp Horse {i}", "jockey": "Nobody New", "exchange": {"back": o, "lay": o + 0.2}}
                    for i, o in enumerate([3, 5, 8, 12, 20, 30])]}]})
    rid = store.race_ids_for(["bf:8.888"])[0]
    live_features.refresh([rid])
    race = store.load_race(get_db(), rid)
    f5 = next(r for r in race["runners"] if r["name"] == "Bsp Horse 5")["features"]
    assert f5["course_runs"] == 1 and f5["distance_runs"] == 1 and f5["course_rate"] > 0.3
    assert f5["priced_runs"] == 1 and f5["place_excess"] > 0 and f5["jockey_runs"] == 0


def test_settings_fall_back_to_env_file(monkeypatch, tmp_path):
    from collectors import betfair
    from racing import bsp_files

    f = tmp_path / "env"
    f.write_text('# comment\nBETFAIR_APP_KEY=abc\nexport BETFAIR_PROXY="socks5h://127.0.0.1:1080"\r\n')
    monkeypatch.setenv("TURNAROUNDIQ_ENV_FILE", str(f))
    monkeypatch.delenv("BETFAIR_PROXY", raising=False)
    assert bsp_files.proxy_setting() == "socks5h://127.0.0.1:1080"
    monkeypatch.setenv("BETFAIR_PROXY", "socks5h://x:1")
    assert bsp_files.proxy_setting() == "socks5h://x:1"           # the environment wins
    assert betfair.setting("NOT_THERE") == ""


def test_full_lay_win_and_place_extra_place_settles():
    from api import tracked
    from api.tracked import ew_place_lay_stake, ew_returns
    from racing import bets as racing_bets

    # £10 EW at 16.0, 5 places 1/5 (place odds 4.0); full lay: win at 17, place (3 places) at 4.0, 2% commission
    lw = tracked.ew_lay_stake(10, 16.0, 17.0, 2, 100)[0]
    lp, lp_liab = ew_place_lay_stake(10, 16.0, 0.2, 4.0, 2)
    assert lp == pytest.approx(5 * 4.0 / 3.98, abs=0.01) and lp_liab == pytest.approx(lp * 3, abs=0.02)
    args = (10, 16.0, 0.2, 17.0, lw, 2, 4.0, lp)
    out = {r: ew_returns(r, *args) for r in ("won", "placed", "extra_place", "lost")}
    assert out["extra_place"] > 10                                  # both place bets pay: the target outcome
    assert abs(out["placed"]) < 1.0 and abs(out["won"]) < 1.5       # covered inside the standard places
    assert out["lost"] < 0 and out["extra_place"] > out["placed"]
    assert ew_returns("extra_place", 10, 16.0, 0.2) == ew_returns("placed", 10, 16.0, 0.2)   # no place lay: same

    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.11", "date": "2026-10-07"}]})
    race = next(r for r in store.races_on("2026-10-07") if r["course"] == "Testcourse")
    with pytest.raises(racing_bets.TrackError):
        racing_bets.track("u_f", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5",
                          lay_mode="full", lay_odds=17.0, commission=2)          # no place lay price
    bet = racing_bets.track("u_f", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5",
                            lay_mode="full", lay_odds=17.0, place_lay_odds=4.0, commission=2)
    assert bet["place_lay_stake"] == pytest.approx(lp, abs=0.01) and bet["std_places"] == 3
    assert bet["snapshot"]["lay"]["mode"] == "full" and "place lay (3 pl)" in bet["notes"]
    assert bet["liability"] == pytest.approx(bet["lay_stake"] * 16 + lp * 3, abs=0.05)
    part = racing_bets.track("u_f", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5",
                             lay_mode="win", lay_odds=17.0, commission=2, lay_pct=100)
    assert part["lay_stake"] == pytest.approx(lw, abs=0.01) and part["place_lay_stake"] is None
    # Horse 6 placed 4th: inside the 5 paid places, outside the 3 standard ones -> extra place
    hid = {r["name"]: r["horse_id"] for r in race["runners"]}
    store.save_results(race["race_id"], [
        {"horse_id": hid["Horse 0"], "won": True, "exchange_sp": 4.0, "placed_within": 3},
        {"horse_id": hid["Horse 6"], "won": False, "exchange_sp": 14.0, "placed_within": 4, "outside_within": 3}])
    racing_bets.auto_settle()
    got = {b["id"]: b for b in tracked_store_list("u_f")}
    assert got[bet["id"]]["result"] == "extra_place"
    assert got[bet["id"]]["actual_profit"] == pytest.approx(-5 + 5 * 3.0 + bet["lay_stake"] * 0.98 + lp * 0.98, abs=0.02)
    assert got[part["id"]]["result"] == "placed"


def test_betfair_place_market_prices_collected(monkeypatch, tmp_path):
    from collectors import betfair

    for k, v in {"BETFAIR_APP_KEY": "k", "BETFAIR_USERNAME": "u", "BETFAIR_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(betfair, "SESSION_FILE", tmp_path / "s.json")
    start = "2026-10-08T13:30:00Z"

    class Fake(_FakeBetfair):
        def post(self, url, data=None, json=None, headers=None, timeout=None):
            if "login" in url:
                return _Resp({"token": "tok", "status": "SUCCESS"})
            m, prm = json["method"].split("/")[-1], json["params"]
            if m == "listMarketCatalogue" and "PLACE" in (prm["filter"].get("marketTypeCodes") or []):
                return _Resp({"result": [
                    {"marketId": "1.901", "marketStartTime": start, "event": {"id": "E9"},
                     "description": {"numberOfWinners": 3}},
                    {"marketId": "1.902", "marketStartTime": start, "event": {"id": "E9"},
                     "description": {"numberOfWinners": 4}}]})
            if m == "listMarketCatalogue":
                return _Resp({"result": [{
                    "marketId": "1.900", "marketName": "1m Hcap", "marketStartTime": start,
                    "event": {"id": "E9", "venue": "Placeford", "countryCode": "GB"},
                    "runners": [{"selectionId": 200 + i, "runnerName": f"Pl {i}", "metadata": {}} for i in range(8)]}]})
            if m == "listMarketBook":
                out = []
                for mid in prm["marketIds"]:
                    mult = {"1.900": 1.0, "1.901": 0.35, "1.902": 0.28}[mid]
                    out.append({"marketId": mid, "runners": [
                        {"selectionId": 200 + i, "status": "ACTIVE", "totalMatched": 50.0,
                         "ex": {"availableToBack": [{"price": round(1 + (o - 1) * mult, 2)}],
                                "availableToLay": [{"price": round(1 + (o - 1) * mult + 0.1, 2)}]}}
                        for i, o in enumerate([3, 4, 6, 8, 11, 15, 21, 34])]})
                return _Resp({"result": out})
            return _Resp({"error": {"code": "?"}})

    betfair.collect(12, betfair.Client(http=Fake()))
    race = next(r for r in store.races_on("2026-10-08") if r["course"] == "Placeford")
    r3 = next(r for r in race["runners"] if r["name"] == "Pl 3")
    assert r3["place_exchange"]["3"] == {"back": 3.45, "lay": 3.55, "volume": 50.0}
    assert r3["place_exchange"]["4"]["back"] == 2.96
    priced = price_race(race, n_sims=2000)
    assert next(r for r in priced["runners"] if r["name"] == "Pl 3")["place_exchange"]["3"]["lay"] == 3.55


def test_min_loss_win_lay_and_full_lay_balance():
    from api.tracked import ew_lay_stake, ew_place_lay_stake, ew_returns

    # £10 EW at 8.0, 1/5 (place 2.4), win lay at 9.0, 2% commission
    pct = 100 * (8.0 + 2.4) / 8.0                                   # "min loss" = 130%
    ls = ew_lay_stake(10, 8.0, 9.0, 2, pct)[0]
    won, placed, lost = (ew_returns(r, 10, 8.0, 0.2, 9.0, ls, 2) for r in ("won", "placed", "lost"))
    assert won == pytest.approx(lost, abs=0.02) and placed > 0       # winner and unplaced cost the same
    ls100 = ew_lay_stake(10, 8.0, 9.0, 2, 100)[0]
    worst100 = min(ew_returns(r, 10, 8.0, 0.2, 9.0, ls100, 2) for r in ("won", "placed", "lost"))
    assert min(won, placed, lost) > worst100                         # smaller worst case than a 100% lay
    assert ew_lay_stake(10, 8.0, 9.0, 2, 500)[0] == pytest.approx(2 * ls100, abs=0.02)   # capped at 200%
    # full lay at the standard stakes: won, placed (standard) and lost come out level
    lw, lp = ew_lay_stake(10, 8.0, 9.0, 2, 100)[0], ew_place_lay_stake(10, 8.0, 0.2, 2.6, 2)[0]
    outs = [ew_returns(r, 10, 8.0, 0.2, 9.0, lw, 2, 2.6, lp) for r in ("won", "placed", "lost")]
    assert max(outs) - min(outs) < 0.05
    assert ew_returns("extra_place", 10, 8.0, 0.2, 9.0, lw, 2, 2.6, lp) > 10


def test_part_lay_defaults_to_min_loss():
    from racing import bets as racing_bets

    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.12", "date": "2026-10-09"}]})
    race = next(r for r in store.races_on("2026-10-09") if r["course"] == "Testcourse")
    bet = racing_bets.track("u_m", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5",
                            lay_mode="win", lay_odds=17.0, commission=2)
    # (16 + 4) / 16 = 125% of the 100% lay: a winner and an unplaced horse cost the same
    assert bet["lay_stake"] == pytest.approx(1.25 * 5 * 16 / 16.98, abs=0.01)
    assert bet["snapshot"]["lay"]["pct"] == pytest.approx(125)


@pytest.mark.parametrize("stake,o,f,lo,plo,c", [(10, 8.0, 0.2, 9.0, 2.6, 2), (20, 4.0, 0.25, 4.3, 1.9, 5),
                                                (6, 26.0, 0.2, 30.0, 6.5, 2)])
def test_lay_stakes_give_the_smallest_worst_case(stake, o, f, lo, plo, c):
    """Brute force over every pair of lay stakes: nothing beats the app's worst case by more than a penny."""
    from api.tracked import ew_lay_stake, ew_place_lay_stake, ew_returns

    part = ew_lay_stake(stake, o, lo, c, 100 * (o + 1 + (o - 1) * f) / o)[0]
    worst = lambda a, b=None: min(ew_returns(r, stake, o, f, lo, a, c, plo if b else None, b)  # noqa: E731
                                  for r in ("won", "placed", "extra_place", "lost"))
    assert worst(part) >= max(worst(x) for x in np.arange(0, 3 * part, 0.01)) - 0.011
    lw, lp = ew_lay_stake(stake, o, lo, c, 100)[0], ew_place_lay_stake(stake, o, f, plo, c)[0]
    grid = max(worst(a, b) for a in np.arange(0.01, 2.5 * lw, lw / 60) for b in np.arange(0.01, 2.5 * lp, lp / 60))
    assert worst(lw, lp) >= grid - 0.011


def test_quote_grades_a_bet_and_exchange_only_races_are_graded():
    from racing import bets as racing_bets

    store.import_card({"timestamp": "2026-10-04T09:00:00Z", "races": [{
        "id": "bf:4.444", "date": "2026-10-10", "time": "15:00", "course": "Quoteford", "name": "1m Hcap",
        "handicap": True, "terms": [{"bookmaker": "Book Q", "places": 5, "fraction": "1/5"}],
        "runners": [{"horse": f"Q{i}", "exchange": {"back": o, "lay": round(o * 1.03, 2)}}
                    for i, o in enumerate([3.5, 5, 7, 9, 11, 13, 17, 21, 26, 34, 41, 51])]}]})
    race = next(r for r in store.races_on("2026-10-10") if r["course"] == "Quoteford")
    priced = price_race(race, n_sims=2000)
    offers = [o for r in priced["runners"] for o in r["offers"]]
    assert offers and all(o["price_source"] == "estimated" and o["grade"] in "ABCD" for o in offers)
    # graded at an estimated bookmaker price: never above the exchange price
    assert all(r["est_book_odds"] <= r["exchange_back"] for r in priced["runners"] if r["est_book_odds"])
    q = racing_bets.quote(race["race_id"], "Q4", "Book Q", 12.0, 5, "1/5")
    assert q["grade"] in "ABCD" and q["places_paid"] == 5 and q["value_from"]
    lower = racing_bets.quote(race["race_id"], "Q4", "Book Q", 6.0, 5, "1/5")
    assert lower["each_way_ev"] < q["each_way_ev"]                     # a shorter price is worth less
    with pytest.raises(racing_bets.TrackError):
        racing_bets.quote(race["race_id"], "Nobody", "Book Q", 12.0, 5, "1/5")


def test_bankroll_pref_and_quote_kelly(monkeypatch):
    from racing import bets as racing_bets

    monkeypatch.setattr(app_module, "user_from_auth", lambda a: "u_bank")
    with TestClient(app_module.app) as client:
        assert client.get("/me/prefs").json()["prefs"]["bankroll"] is None
        assert client.patch("/me/prefs", json={"bankroll": 500}).json()["prefs"]["bankroll"] == 500
        assert client.patch("/me/prefs", json={"bankroll": -5}).status_code == 422
    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.13", "date": "2026-10-11"}]})
    race = next(r for r in store.races_on("2026-10-11") if r["course"] == "Testcourse")
    q = racing_bets.quote(race["race_id"], "Horse 6", "Book Z", 16.0, 5, "1/5")
    assert set(q["stakes"]) == {"quarter", "half", "full"} and q["stakes"]["quarter"]["each_way_pct"] <= 5


def test_estimated_bookmaker_prices():
    from racing import market as m
    import importlib.util

    p = m.devig_power([3.5, 5, 7, 9, 11, 13, 17, 21, 26, 34, 41, 51])
    est = m.estimated_book_odds(p)
    fair = 1 / p
    assert all(e < f for e, f in zip(est, fair))                          # always shorter than fair
    assert all(e in m.UK_PRICES for e in est)                             # real UK prices
    assert (fair[-1] / est[-1]) > (fair[0] / est[0])                       # outsiders cut more (longshot bias)
    q = m.early_book_from_fair(p, 1.22)
    cut = 1 - (1 / q - 1) / (1 / p - 1)
    assert abs(q.sum() - 1.22) < 1e-6 and cut[-1] - cut[0] < 0.08            # ...but not SP-harsh
    assert m.best_price_overround(14) == pytest.approx(1.21) and m.best_price_overround(40) == 1.35
    assert m.best_price_overround(14, 0.01) == pytest.approx(1.14)
    # graded on an estimated price: never an A (that needs a real price)
    race = {"handicap": True, "terms": [{"bookmaker": "B", "places": 5, "fraction": "1/5"}],
            "runners": [{"name": f"E{i}", "exchange": {"back": o, "lay": round(o * 1.03, 2), "volume": 5000}}
                        for i, o in enumerate([5, 7.2, 8.6, 10, 11.4, 12.9, 15.7, 18.6, 21.5, 24.3, 30, 37, 49, 73])]}
    offers = [o for r in price_race(race, {"fitted": True, "n_races": 5000, "best_price_rate": 0.006}, n_sims=4000)["runners"] for o in r["offers"]]
    assert all(o["price_source"] == "estimated" and o["grade"] != "A" for o in offers)
    assert any(o["grade"] == "B" for o in offers)
    q = m.book_from_fair(p, 1.25)
    assert abs(q.sum() - 1.25) < 1e-6
    assert m.typical_overround(12, {"8": 1.15, "12": 1.24, "16": 1.31}) == 1.24
    spec = importlib.util.spec_from_file_location("ov", "scripts/stables_overround.py")
    ov = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ov)
    races = [{"runners": [{"odds": o} for o in (2.0, 4.0, 5.0, 10.0)]}] * 40
    assert ov.fit(races) == {"4": round(0.5 + 0.25 + 0.2 + 0.1, 4)}


def test_settled_bet_result_can_be_corrected_or_reopened():
    from api import tracked
    from racing import bets as racing_bets

    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.14", "date": "2026-10-12"}]})
    race = next(r for r in store.races_on("2026-10-12") if r["course"] == "Testcourse")
    bet = racing_bets.track("u_fix", race["race_id"], "Horse 6", "Book Z", 16.0, 10, 5, "1/5")
    assert tracked.settle_tracked("u_fix", bet["id"], "lost")["actual_profit"] == -10
    fixed = tracked.settle_tracked("u_fix", bet["id"], "placed")           # wrong result corrected
    assert fixed["result"] == "placed" and fixed["actual_profit"] == pytest.approx(-5 + 5 * 3.0)
    back = tracked.reopen_tracked("u_fix", bet["id"])
    assert back["status"] == "open" and back["result"] is None and back["actual_profit"] is None
    assert tracked.reopen_tracked("someone_else", bet["id"]) is None


def test_quote_reports_the_prices_it_used():
    from racing import bets as racing_bets

    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.15", "date": "2026-10-13"}]})
    race = next(r for r in store.races_on("2026-10-13") if r["course"] == "Testcourse")
    q = racing_bets.quote(race["race_id"], "Horse 6", "Book Z", 26.0, 5, "1/5")
    assert 0 < q["win_probability"] < 1 and "exchange_back" in q and "est_book_odds" in q


def test_unformed_betfair_market_is_not_trusted():
    from racing import market as m

    # 5.1 back against an empty lay book (600) is not a 10/1 shot: use the back price, not the midpoint
    assert not m.formed(5.1, 600) and m.formed(5.0, 5.2)
    assert m.exchange_price_prob(5.1, 600) == pytest.approx(1 / 5.1)
    assert m.exchange_price_prob(5.0, 5.2) == pytest.approx(0.5 * (1 / 5.0 + 1 / 5.2))
    thin = {"handicap": True, "terms": [{"bookmaker": "B", "places": 4, "fraction": "1/5"}],
            "runners": [{"name": f"T{i}", "exchange": {"back": o, "lay": 600.0}} for i, o in enumerate([3, 5, 7, 9, 12, 15, 21, 26])]}
    out = price_race(thin, {"fitted": True, "n_races": 1000}, n_sims=2000)
    assert out["market_thin"] and all(o["grade"] not in "AB" for r in out["runners"] for o in r["offers"])
    assert all(r["market_formed"] is False for r in out["runners"])
    firm = {**thin, "runners": [{"name": f"T{i}", "exchange": {"back": o, "lay": round(o * 1.04, 2)}}
                                for i, o in enumerate([3, 5, 7, 9, 12, 15, 21, 26])]}
    assert not price_race(firm, n_sims=2000)["market_thin"]
    # a race formed at the front with only its 50/1+ shots on empty books is not thin
    odds = [3, 5, 7, 9, 12, 15, 21, 26, 51, 67, 101]
    tail = {**thin, "runners": [{"name": f"T{i}", "exchange": {"back": o, "lay": round(o * 1.04, 2) if o < 50 else 600.0}}
                                for i, o in enumerate(odds)]}
    out = price_race(tail, n_sims=2000)
    assert not out["market_thin"] and out["market_formed_share"] >= 0.9


def test_kelly_caps_longshots_and_skips_c_d_grades():
    from racing import kelly as K

    assert K.stake_cap(4.0) == 0.05 and K.stake_cap(9.0) == 0.05
    assert K.stake_cap(26.0) == pytest.approx(0.45 / 26) and K.stake_cap(51.0) < 0.01
    big = K.robust_stakes(0.15, 0.6, 0.0, 0.0, 26.0, 6.0)         # a big (too good) edge at 25/1
    assert big["full"]["each_way_pct"] <= 100 * 0.45 / 26 + 1e-9
    out = price_race({"handicap": True, "terms": [{"bookmaker": "B", "places": 4, "fraction": "1/5"}],
                      "runners": [{"name": f"K{i}", "win_odds": o} for i, o in enumerate(ODDS)]}, n_sims=2000)
    for o in (o for r in out["runners"] for o in r["offers"]):
        if o["grade"] in "CD":
            assert o["recommended_stake_pct"] == 0 and o["stakes"]["quarter"]["each_way_pct"] == 0


def test_bet_sp_from_bsp_files_and_bookmaker_spellings(monkeypatch):
    from datetime import date, timedelta
    from racing import bets as racing_bets, bsp_files

    day = (date.today() - timedelta(days=2)).isoformat()
    store.import_card({**CARD, "races": [{**CARD["races"][0], "id": "bf:9.71", "date": day}]})
    race = next(r for r in store.races_on(day) if r["course"] == "Testcourse")
    racing_bets.track("u_sp", race["race_id"], "Horse 3", "Sky Bet", 11.0, 10, 4, "1/5")
    racing_bets.track("u_sp", race["race_id"], "Horse 4", "sky  bet", 13.0, 10, 4, "1/5")
    dt = date.fromisoformat(day).strftime("%d-%m-%Y")
    csv_text = ("EVENT_ID,MENU_HINT,EVENT_NAME,EVENT_DT,SELECTION_ID,SELECTION_NAME,WIN_LOSE,BSP\n"
                f"1,UK / Test,1m Hcap,{dt} 14:00,11,Horse 3,0,10.0\n"
                f"1,UK / Test,1m Hcap,{dt} 14:00,12,Horse 4 (IRE),0,12.5\n"
                "2,UK / Test,1m Hcap,01-01-2020 14:00,13,Horse 5,0,99.0\n")      # another day's race: ignored
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    # the file named the day AFTER the racing holds it (as Betfair's do)
    monkeypatch.setattr(bsp_files, "fetch", lambda region, market, d, pause=0.3:
                        csv_text if region == "uk" and d.isoformat() == nxt else "")
    assert bsp_files.fill_bet_sp() >= 2
    assert bsp_files.fill_bet_sp() == 0                       # already filled
    rep = racing_bets.report("u_sp")
    sps = store.race_sps(race["race_id"])
    hid = {r["name"]: r["horse_id"] for r in race["runners"]}
    assert sps[hid["Horse 3"]] == 10.0 and sps[hid["Horse 4"]] == 12.5
    assert list(rep["by_bookmaker"]) == ["Sky Bet"] and rep["by_bookmaker"]["Sky Bet"]["bets"] == 2


def test_estimate_learns_from_prices_taken(monkeypatch):
    from datetime import date, timedelta
    from racing import bets as racing_bets

    day = (date.today() + timedelta(days=3)).isoformat()
    store.import_card({"timestamp": f"{day}T08:00:00Z", "races": [{
        "id": "bf:9.81", "date": day, "time": "15:00", "course": "Learnford", "handicap": True,
        "runners": [{"horse": f"L{i}", "exchange": {"back": o, "lay": round(o * 1.03, 2), "volume": 900}}
                    for i, o in enumerate([4, 6, 8, 10, 13, 17, 21, 26, 34, 51])]}]})
    race = next(r for r in store.races_on(day) if r["course"] == "Learnford")
    conn = store.get_db()
    conn.execute("DELETE FROM rac_bets")
    conn.commit()
    assert store.learned_price_rate(conn) is None
    snaps = []
    for i in range(store.MIN_PRICE_BETS):
        b = racing_bets.track("u_learn", race["race_id"], f"L{i % 5}", "Book Q", 7.0, 10, 4, "1/5")
        snaps.append(b["snapshot"]["runner"])
    assert all(s.get("est_book_odds") and s.get("est_overround") for s in snaps)
    rate = store.learned_price_rate(conn)
    conn.close()
    assert rate is not None and 0.005 <= rate <= 0.035
    assert store.latest_calibration().get("best_price_rate") == rate


def test_shadow_tracker_records_shown_runners_and_reports_by_grade():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from racing import shadow

    day = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
    odds = [4, 6, 8, 10, 13, 17, 21, 26, 34, 51]
    store.import_card({"timestamp": f"{day}T08:00:00Z", "races": [{
        "id": "bf:9.91", "date": day, "time": "23:59", "course": "Shadowford", "handicap": True,
        "terms": [{"bookmaker": "Book S", "places": 4, "fraction": "1/5"},
                  {"bookmaker": "Book T", "places": 4, "fraction": "1/5"},
                  {"bookmaker": "Book U", "places": 5, "fraction": "1/5"}],
        "runners": [{"horse": f"S{i}", "exchange": {"back": o, "lay": round(o * 1.03, 2), "volume": 900}}
                    for i, o in enumerate(odds)]}]})
    race = next(r for r in store.races_on(day) if r["course"] == "Shadowford")
    n = shadow.record_today(n_sims=2000)
    conn = store.get_db()
    got = conn.execute("SELECT COUNT(*), COUNT(DISTINCT places) FROM rac_shadow WHERE race_id = ?",
                       (race["race_id"],)).fetchone()
    conn.close()
    assert n >= 20 and got == (20, 2)                 # one row per runner per set of terms (S & T share)
    assert shadow.record_today(n_sims=2000) >= 20     # re-run updates, no duplicates
    hid = {r["name"]: r["horse_id"] for r in race["runners"]}
    store.save_results(race["race_id"], [
        {"horse_id": hid[f"S{i}"], "won": i == 2, "placed_within": 4 if i in (0, 2, 5, 7) else None,
         "outside_within": 4 if i not in (0, 2, 5, 7) else None, "exchange_sp": float(o)} for i, o in enumerate(odds)])
    rep = shadow.report()
    # 4-place rows all settle; 5-place ones only where Betfair says (top 4 = placed, else unknown)
    assert rep["all"]["settled"] >= 14 and rep["by_grade"] and rep["by_odds"]
    assert rep["all"]["avg_clv"] is not None          # every runner has an SP: value at SP computed


def test_recal_from_bsp_files_rows_and_fit():
    import importlib.util
    from racing import backtest

    spec = importlib.util.spec_from_file_location("rb", "scripts/stables_recal_bsp.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    rng = np.random.default_rng(4)
    head = "EVENT_ID,MENU_HINT,EVENT_NAME,EVENT_DT,SELECTION_ID,SELECTION_NAME,WIN_LOSE,BSP\n"
    win, place = [head], [head]
    for e in range(400):
        n = 8
        p = rng.dirichlet(np.ones(n) * 2)
        order = list(rng.choice(n, n, replace=False, p=p))
        dt = f"01-10-2026 {10 + e // 60}:{e % 60:02d}"
        for i in range(n):
            win.append(f"{e},UK / Test,1m Hcap,{dt},{i},H{e}x{i},{int(order[0] == i)},{1 / p[i]:.2f}\n")
            place.append(f"{e},UK / Test,1m Hcap,{dt},{i},H{e}x{i},{int(i in order[:3])},{1 / min(.95, 3 * p[i]):.2f}\n")
    races = backtest.bsp_races("".join(win), "".join(place))
    assert len(races) == 400 and races[0]["name"] == "1m Hcap"
    rows = rb.rows_for(races, {}, 300)
    assert len(rows["place_y"]) == 3200 and rows["place_y"].sum() == 1200
    new = rb.recalibrate.fit(rows)
    assert new["fitted"] and rb.log_loss(rb.scored(rows, new), rows["place_y"]) <= rb.log_loss(rows["place_p"], rows["place_y"]) + 1e-3
