"""
api-sports.io historical backfill + import, against a mocked API.

Shapes follow API-Football v3 (/leagues, /fixtures, /fixtures?ids=). Confirm
against the live API with:  python -u collectors/backfill_apisports.py --probe
"""

import sqlite3

import pandas as pd
import pytest

import database
from collectors import apisports as af
from collectors import backfill_apisports as bf
from training import import_historical_events as imp

ARS, CHE, LIV, EVE, TOT, FUL = 42, 49, 40, 45, 47, 36


def goal(team_id, name, minute, detail="Normal Goal", extra=None):
    return {"time": {"elapsed": minute, "extra": extra}, "team": {"id": team_id, "name": name},
            "player": {"name": f"p{minute}"}, "type": "Goal", "detail": detail, "comments": None}


def fixture(fid, date, home, away, hg, ag):
    return {"fixture": {"id": fid, "date": f"{date}T15:00:00+00:00"},
            "league": {"country": "England"},
            "teams": {"home": {"id": home[0], "name": home[1]},
                      "away": {"id": away[0], "name": away[1]}},
            "goals": {"home": hg, "away": ag},
            "score": {"fulltime": {"home": hg, "away": ag}}}


FIXTURES = {
    2024: [
        # 2-up then draw, incl. a missed penalty that must not count
        fixture(1, "2024-09-01", (ARS, "Arsenal"), (CHE, "Chelsea"), 2, 2),
        # own goal by an Everton player, event tagged with Everton -> Liverpool 1-0
        fixture(2, "2024-09-08", (LIV, "Liverpool"), (EVE, "Everton"), 1, 0),
        # events can't reproduce 3-0 -> skipped
        fixture(3, "2024-09-15", (TOT, "Tottenham"), (FUL, "Fulham"), 3, 0),
    ],
    2025: [fixture(4, "2025-09-01", (CHE, "Chelsea"), (ARS, "Arsenal"), 0, 0)],
    2026: [fixture(5, "2026-09-01", (ARS, "Arsenal"), (LIV, "Liverpool"), 1, 0)],
}
EVENTS = {
    1: [goal(ARS, "Arsenal", 10), goal(ARS, "Arsenal", 45, extra=2),
        goal(CHE, "Chelsea", 50, detail="Missed Penalty"),
        goal(CHE, "Chelsea", 60), goal(CHE, "Chelsea", 85)],
    2: [goal(EVE, "Everton", 33, detail="Own Goal")],
    3: [goal(TOT, "Tottenham", 5)],
    4: [],
    5: [goal(ARS, "Arsenal", 70)],
}


class FakeAPI:
    def __init__(self, remaining=10_000):
        self.calls = []
        self.remaining = remaining

    def __call__(self, path, params=None):
        if af._state["remaining_day"] is not None and af._state["remaining_day"] <= af.RESERVE:
            raise af.QuotaExhausted("reserve")
        self.calls.append((path, dict(params or {})))
        self.remaining -= 1
        af._state["remaining_day"] = self.remaining
        af._state["calls"] += 1
        params = params or {}
        if path == "/leagues":
            return {"response": [{"seasons": [
                {"year": y, "current": y == 2026, "coverage": {"fixtures": {"events": True}}}
                for y in (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026)]}]}
        if path == "/fixtures" and "ids" in params:
            ids = [int(i) for i in params["ids"].split("-")]
            assert len(ids) <= bf.BATCH
            out = []
            for items in FIXTURES.values():
                for it in items:
                    if it["fixture"]["id"] in ids:
                        out.append({**it, "events": EVENTS[it["fixture"]["id"]]})
            return {"response": out}
        if path == "/fixtures":
            return {"response": FIXTURES.get(params["season"], [])}
        raise AssertionError(path)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "GINF", tmp_path / "ginf_apisports.csv")
    monkeypatch.setattr(bf, "EVENTS", tmp_path / "events_apisports.csv")
    monkeypatch.setattr(bf, "SKIPPED", tmp_path / "skipped.csv")
    monkeypatch.setattr(bf, "DONE", tmp_path / "done.csv")
    monkeypatch.setattr(bf, "SEASONS_CACHE", tmp_path / "seasons.json")
    monkeypatch.setattr(imp, "DATA_DIR", tmp_path)
    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "test")
    monkeypatch.setattr(af, "RESERVE", 5)
    af._state.update({"remaining_day": None, "calls": 0})
    fake = FakeAPI()
    monkeypatch.setattr(af, "api_get", fake)
    return fake


def run(*extra):
    return bf.main(["--league-id", "39", *extra])


def test_season_selection_last_five_completed():
    seasons = [{"year": y, "current": y == 2026, "events_covered": True}
               for y in range(2026, 2017, -1)]
    assert [s["year"] for s in bf.pick_seasons(seasons)] == [2025, 2024, 2023, 2022, 2021]
    assert [s["year"] for s in bf.pick_seasons(seasons, 5, True)] == [2026, 2025, 2024, 2023, 2022, 2021]


def test_backfill_writes_validated_matches(api):
    assert run() == 0
    ginf = pd.read_csv(bf.GINF)
    assert sorted(ginf["id_odsp"]) == ["af-1", "af-2", "af-4"]  # af-5 is current season
    ev = pd.read_csv(bf.EVENTS)
    m1 = ev[ev.id_odsp == "af-1"]
    assert list(m1["side"]) == [1, 1, 2, 2]          # missed penalty dropped
    assert list(m1["time"]) == [10, 45, 60, 85]      # 45+2 stays in first half
    og = ev[ev.id_odsp == "af-2"]
    assert list(og["side"]) == [1] and list(og["event_team"]) == ["Liverpool"]
    skipped = pd.read_csv(bf.SKIPPED)
    assert list(skipped["id_odsp"]) == ["af-3"]
    # exactly the last 5 completed seasons were listed
    listed = sorted(p["season"] for path, p in api.calls if path == "/fixtures" and "season" in p)
    assert listed == [2021, 2022, 2023, 2024, 2025]


def test_resume_makes_no_event_calls(api):
    run()
    before = len(api.calls)
    assert run() == 0
    new = api.calls[before:]
    # finished backfill: second run costs nothing
    assert new == []


def test_include_current_is_opt_in(api):
    assert run("--include-current") == 0
    assert "af-5" in set(pd.read_csv(bf.GINF)["id_odsp"])


def test_season_list_cache_expires(api):
    run()
    cache = bf._load_seasons_cache()
    cache["39"]["at"] = "2000-01-01T00:00:00+00:00"
    bf.SEASONS_CACHE.write_text(__import__("json").dumps(cache))
    before = len(api.calls)
    run()
    assert [c[0] for c in api.calls[before:]] == ["/leagues"]


def test_stops_at_reserve_and_resumes(api):
    api.remaining = 9  # reserve 5: /leagues + a few fixture lists, then stop
    assert run() == bf.EXIT_PARTIAL
    got = len(pd.read_csv(bf.GINF)) if bf.GINF.exists() else 0
    assert got < 3
    api.remaining = 10_000
    af._state["remaining_day"] = None
    assert run() == 0
    assert len(pd.read_csv(bf.GINF)) == 3


def test_own_goal_rule_as_is_also_supported():
    # If the API tagged the own goal with the credited team instead:
    events = [goal(LIV, "Liverpool", 33, detail="Own Goal")]
    rows, rule, reason = bf.resolve_goals(events, LIV, EVE, "Liverpool", "Everton", 1, 0)
    assert reason is None and rule == "as_is" and rows[0][1] == 1


def test_missing_key_exits(monkeypatch):
    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "")
    with pytest.raises(SystemExit):
        bf.main(["--league-id", "39"])


def _historical_db():
    conn = sqlite3.connect(database.DB_NAME)
    conn.execute("DROP TABLE IF EXISTS historical_matches")
    conn.execute("DROP TABLE IF EXISTS historical_events")
    conn.execute("""CREATE TABLE historical_matches (match_id TEXT, date TEXT, league TEXT,
        season TEXT, country TEXT, home_team TEXT, away_team TEXT, final_home INTEGER,
        final_away INTEGER, odd_h REAL, odd_d REAL, odd_a REAL)""")
    conn.execute("""CREATE TABLE historical_events (match_id TEXT, minute INTEGER,
        event_type TEXT, event_type2 TEXT, side INTEGER, team TEXT, player TEXT,
        is_goal INTEGER, situation TEXT)""")
    conn.commit()
    return conn


def test_import_prefers_apisports_and_dedupes(api, tmp_path):
    run()
    # Older one-off backfill has the same fixture 1 under another id + one extra match.
    pd.DataFrame([
        {"id_odsp": "api-1", "date": "2024-09-01", "league": "Premier League", "season": 2024,
         "country": "", "ht": "Arsenal", "at": "Chelsea", "fthg": 2, "ftag": 2,
         "odd_h": "", "odd_d": "", "odd_a": ""},
        {"id_odsp": "api-9", "date": "2019-01-01", "league": "Premier League", "season": 2018,
         "country": "", "ht": "Leeds", "at": "Wolves", "fthg": 0, "ftag": 0,
         "odd_h": "", "odd_d": "", "odd_a": ""},
    ]).to_csv(tmp_path / "ginf_api.csv", index=False)
    pd.DataFrame([{"id_odsp": "api-1", "time": 12, "event_type": 1, "event_type2": "",
                   "side": 1, "event_team": "Arsenal", "player": "x", "is_goal": 1,
                   "situation": ""}]).to_csv(tmp_path / "events_api.csv", index=False)
    # crash-and-refetch duplicate goal rows
    pd.read_csv(bf.EVENTS).query("id_odsp == 'af-1'").to_csv(
        bf.EVENTS, mode="a", header=False, index=False)

    conn = _historical_db()
    imp.run("all")
    ids = sorted(r[0] for r in conn.execute("SELECT match_id FROM historical_matches"))
    assert ids == ["af-1", "af-2", "af-4", "api-9"]
    goals = dict(conn.execute(
        "SELECT match_id, COUNT(*) FROM historical_events GROUP BY match_id").fetchall())
    assert goals == {"af-1": 4, "af-2": 1}
    conn.close()


def test_import_refuses_to_shrink(api):
    run()
    conn = _historical_db()
    conn.executemany("INSERT INTO historical_matches (match_id) VALUES (?)",
                     [(f"old-{i}",) for i in range(100)])
    conn.commit()
    with pytest.raises(SystemExit) as exc:
        imp.run("apisports")
    assert exc.value.code == 4
    imp.run("apisports", allow_shrink=True)
    assert conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == 3
    conn.close()


def test_network_drop_retries_then_succeeds(monkeypatch):
    import requests
    calls = {"n": 0}

    class Resp:
        status_code = 200
        headers = {"x-ratelimit-requests-remaining": "7000"}
        text = ""

        def raise_for_status(self):
            pass

        def json(self):
            return {"response": [], "errors": []}

    class Garbled(Resp):
        def json(self):
            raise ValueError("Expecting value: line 1 column 1")

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.ConnectionError("reset by peer")
        if calls["n"] == 2:
            return Garbled()
        return Resp()

    monkeypatch.setattr(af.requests, "get", flaky)
    monkeypatch.setattr(af.time, "sleep", lambda s: None)
    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "k")
    assert af.api_get("/fixtures", {"ids": "1"}) == {"response": [], "errors": []}
    assert calls["n"] == 3


def test_network_down_stops_cleanly_and_keeps_progress(api, monkeypatch):
    def down(path, params=None):
        if "ids" in (params or {}):
            raise af.NetworkError("ConnectionError")
        return FakeAPI.__call__(api, path, params)

    monkeypatch.setattr(af, "api_get", down)
    assert run() == bf.EXIT_PARTIAL


def test_unexpected_error_stops_cleanly(api, monkeypatch):
    def boom(*a, **k):
        raise KeyError("fixture")

    monkeypatch.setattr(bf, "process_batch", boom)
    assert run() == bf.EXIT_PARTIAL
