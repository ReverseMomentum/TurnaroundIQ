"""
TheStatsAPI historical collection + import, against a mocked API.

Response shapes mirror what collectors/thestatsapi.py already parses; confirm
them against the live API with:  python -u collectors/backfill_thestatsapi.py --probe
"""

import sqlite3

import pandas as pd
import pytest

import database
from collectors import backfill_thestatsapi as bf
from collectors import thestatsapi as ts
from training import import_historical_events as imp

MATCHES = [
    # 2-up then draw: Arsenal 2-0 up, finishes 2-2
    {"id": 1, "utc_date": "2024-09-01T15:00:00Z",
     "home": {"name": "Arsenal", "score": 2}, "away": {"name": "Chelsea", "score": 2}},
    # clean 1-0
    {"id": 2, "utc_date": "2024-09-08T15:00:00Z",
     "home": {"name": "Liverpool", "score": 1}, "away": {"name": "Everton", "score": 0}},
    # timeline missing a goal -> must be skipped, not written goal-less
    {"id": 3, "utc_date": "2024-09-15T15:00:00Z",
     "home": {"name": "Spurs", "score": 3}, "away": {"name": "Fulham", "score": 0}},
]


def _goal(team, minute):
    return {"type": "goal", "minute": minute, "team": {"name": team},
            "player": {"name": f"{team} {minute}"}, "period": "1H" if minute <= 45 else "2H"}


TIMELINES = {
    1: [_goal("Arsenal", 10), _goal("Arsenal", 30), _goal("Chelsea", 60), _goal("Chelsea", 85)],
    2: [_goal("Liverpool", 55)],
    3: [_goal("Spurs", 5), _goal("Spurs", 50)],
}


class FakeAPI:
    def __init__(self, quota=None):
        self.calls = 0
        self.quota = quota

    def __call__(self, path, params=None):
        self.calls += 1
        if self.quota is not None and self.calls > self.quota:
            raise ts.QuotaExhausted("429 x4")
        if path.endswith("/seasons"):
            return {"data": [{"id": "s2024", "name": "2024/2025", "start_year": 2024}]}
        if path == "/football/matches":
            return {"data": MATCHES, "meta": {"total_pages": 1}}
        if path.endswith("/timeline"):
            mid = int(path.split("/")[-2])
            return {"data": {"events": TIMELINES[mid]}}
        raise AssertionError(path)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "GINF_API", tmp_path / "ginf_api.csv")
    monkeypatch.setattr(bf, "EVENTS_API", tmp_path / "events_api.csv")
    monkeypatch.setattr(bf, "SKIPPED", tmp_path / "skipped.csv")
    monkeypatch.setattr(imp, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ts, "THESTATSAPI_KEY", "test")
    monkeypatch.setattr(ts, "find_competition_id", lambda name: "comp_pl")
    bf._seasons_cache.clear()
    fake = FakeAPI()
    monkeypatch.setattr(ts, "api_get", fake)
    return fake


def run(*extra):
    return bf.main(["--league", "Premier League", "--year", "2024", *extra])


def test_collects_complete_matches_and_skips_incomplete(api):
    assert run() == 0
    ginf = pd.read_csv(bf.GINF_API)
    assert sorted(ginf["id_odsp"]) == ["ts-1", "ts-2"]
    events = pd.read_csv(bf.EVENTS_API)
    assert len(events[events.id_odsp == "ts-1"]) == 4
    skipped = pd.read_csv(bf.SKIPPED)
    assert list(skipped["id_odsp"]) == ["ts-3"]
    assert skipped["reason"][0].startswith("timeline_2-0_vs_final_3-0")


def test_resume_does_not_refetch(api):
    run()
    calls = api.calls
    assert run() == 0
    # second run: seasons cached + one list call, zero timeline calls
    assert api.calls - calls == 1


def test_quota_stop_is_partial_and_resumable(api):
    api.quota = 3  # seasons, list, one timeline
    assert run() == bf.EXIT_PARTIAL
    assert list(pd.read_csv(bf.GINF_API)["id_odsp"]) == ["ts-1"]
    api.quota = None
    assert run() == 0
    assert sorted(pd.read_csv(bf.GINF_API)["id_odsp"]) == ["ts-1", "ts-2"]


def test_max_matches_cap(api):
    assert run("--max-matches", "1") == bf.EXIT_PARTIAL
    assert len(pd.read_csv(bf.GINF_API)) == 1


def test_missing_key_exits(monkeypatch):
    monkeypatch.setattr(ts, "THESTATSAPI_KEY", "")
    with pytest.raises(SystemExit):
        bf.main(["--league", "Premier League"])


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


def test_import_prefers_thestatsapi_and_dedupes(api, tmp_path):
    run()
    # Legacy FBref copy of fixture 1 (different id) plus one FBref-only match.
    pd.DataFrame([
        {"id_odsp": "fb-1", "date": "2024-09-01", "league": "Premier League", "season": 2024,
         "country": "", "ht": "Arsenal", "at": "Chelsea", "fthg": 2, "ftag": 2,
         "odd_h": "", "odd_d": "", "odd_a": ""},
        {"id_odsp": "fb-9", "date": "2019-01-01", "league": "Premier League", "season": 2018,
         "country": "", "ht": "Leeds", "at": "Wolves", "fthg": 0, "ftag": 0,
         "odd_h": "", "odd_d": "", "odd_a": ""},
    ]).to_csv(tmp_path / "ginf.csv", index=False)
    pd.DataFrame([
        {"id_odsp": "fb-1", "time": 12, "event_type": 1, "event_type2": "", "side": 1,
         "event_team": "Arsenal", "player": "x", "is_goal": 1, "situation": ""},
    ]).to_csv(tmp_path / "events.csv", index=False)
    # Simulate a crash-and-refetch that appended ts-2's goal twice.
    pd.read_csv(bf.EVENTS_API).query("id_odsp == 'ts-2'").to_csv(
        bf.EVENTS_API, mode="a", header=False, index=False)

    conn = _historical_db()
    imp.run("all")
    ids = sorted(r[0] for r in conn.execute("SELECT match_id FROM historical_matches"))
    assert ids == ["fb-9", "ts-1", "ts-2"]
    goals = dict(conn.execute(
        "SELECT match_id, COUNT(*) FROM historical_events GROUP BY match_id").fetchall())
    assert goals == {"ts-1": 4, "ts-2": 1}
    conn.close()


def test_import_refuses_to_shrink(api):
    run()
    conn = _historical_db()
    conn.executemany("INSERT INTO historical_matches (match_id) VALUES (?)",
                     [(f"old-{i}",) for i in range(100)])
    conn.commit()
    with pytest.raises(SystemExit) as exc:
        imp.run("thestatsapi")
    assert exc.value.code == 4
    assert conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == 100
    imp.run("thestatsapi", allow_shrink=True)
    assert conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == 2
    conn.close()
