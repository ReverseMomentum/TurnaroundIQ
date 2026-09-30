"""Pre-match odds from api-sports: best UK back, estimated lay, and the API picking them up."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import database
from collectors import apisports as af
from collectors import odds_apisports as oa


def _bk(name, home, draw, away):
    return {"name": name, "bets": [
        {"id": 1, "name": "Match Winner", "values": [
            {"value": "Home", "odd": str(home)},
            {"value": "Draw", "odd": str(draw)},
            {"value": "Away", "odd": str(away)},
        ]},
        {"id": 5, "name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.8"}]},
    ]}


BOOKS = [
    _bk("Bet365", 2.10, 3.40, 3.60),
    _bk("William Hill", 2.15, 3.30, 3.50),
    _bk("Pinnacle", 2.12, 3.55, 3.75),
    _bk("1xBet", 2.30, 3.50, 3.70),  # not a UK book: never the best back
]


def test_tick_up_follows_betfair_ladder():
    assert oa.tick_up(2.00) == 2.02
    assert oa.tick_up(1.955) == 1.96
    assert oa.tick_up(3.5) == 3.55
    assert oa.tick_up(5.0) == 5.1
    assert oa.tick_up(12.0) == 12.5


def test_parse_keeps_match_winner_only():
    books = oa.parse_bookmakers(BOOKS)
    assert set(books) == {"Bet365", "William Hill", "Pinnacle", "1xBet"}
    assert books["Bet365"] == {"home": 2.10, "draw": 3.40, "away": 3.60}


def test_best_uk_back_and_lay_from_pinnacle_fair_price():
    row = oa.summarise(oa.parse_bookmakers(BOOKS))
    assert (row["home_back"], row["home_book"]) == (2.15, "William Hill")
    assert (row["away_back"], row["away_book"]) == (3.60, "Bet365")
    assert row["fair_source"] == "pinnacle"
    # Pinnacle 2.12/3.55/3.75 has ~2% margin -> fair home ~2.17 -> +1 tick
    assert 2.15 < row["home_lay_est"] < 2.25
    # the lay estimate sits above the fair price, as an exchange lay does
    fair = oa._fair({"home": 2.12, "draw": 3.55, "away": 3.75})
    assert row["home_lay_est"] > fair["home"]
    assert row["away_lay_est"] > fair["away"]


def test_no_sharp_book_uses_median_and_no_uk_book_gives_no_back():
    row = oa.summarise(oa.parse_bookmakers([_bk("1xBet", 2.3, 3.5, 3.7), _bk("Marathonbet", 2.2, 3.4, 3.6)]))
    assert row["fair_source"].startswith("median")
    assert row["home_back"] is None
    assert oa.side_prices(row, True) is None


@pytest.fixture
def fresh_table():
    conn = sqlite3.connect(database.DB_NAME)
    conn.execute("DROP TABLE IF EXISTS fixture_odds")
    oa.ensure_table(conn)
    conn.commit()
    return conn


def test_collector_run_saves_odds(fresh_table, monkeypatch):
    fresh_table.close()
    ko = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    def fake_get(path, params=None):
        if path == "/fixtures":
            return {"response": [
                {"league": {"id": 39}, "fixture": {"id": 111, "date": ko}},
                {"league": {"id": 99999}, "fixture": {"id": 222, "date": ko}},  # unsupported league
            ]}
        assert path == "/odds" and params["fixture"] == 111
        return {"response": [{"bookmakers": BOOKS}]}

    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "test")
    monkeypatch.setattr(af, "api_get", fake_get)
    assert oa.main(["--hours", "48"]) == 0
    stored = oa.load_odds(["111", "222"])
    assert list(stored) == ["111"]
    assert stored["111"]["home_book"] == "William Hill"

    # a second run straight after skips the freshly priced fixture (no wasted calls)
    summary = oa.refresh(48)
    assert summary["skipped_fresh"] == 1 and summary["saved"] == 0


def test_only_games_inside_the_window_are_priced(fresh_table, monkeypatch):
    fresh_table.close()
    now = datetime.now(timezone.utc)
    soon, later = (now + timedelta(hours=3)).isoformat(), (now + timedelta(hours=30)).isoformat()
    priced = []

    def fake_get(path, params=None):
        if path == "/fixtures":
            return {"response": [
                {"league": {"id": 39}, "fixture": {"id": 1, "date": soon}},
                {"league": {"id": 39}, "fixture": {"id": 2, "date": later}},
            ]}
        priced.append(params["fixture"])
        return {"response": [{"bookmakers": BOOKS}]}

    monkeypatch.setattr(af, "API_FOOTBALL_KEY", "test")
    monkeypatch.setattr(af, "api_get", fake_get)
    oa.refresh(24)
    assert priced == [1]


def test_stale_odds_are_ignored(fresh_table):
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    fresh_table.execute(
        "INSERT INTO fixture_odds (match_id, home_back, home_book, home_lay_est, updated_at) VALUES (?,?,?,?,?)",
        ("333", 2.0, "Bet365", 2.1, old),
    )
    fresh_table.commit()
    fresh_table.close()
    assert oa.load_odds(["333"]) == {}


def test_api_fixtures_use_real_back_and_flag_estimated_lay(fresh_table, monkeypatch):
    from api import app as app_module
    from models.opportunities_engine import build_opportunity

    conn = fresh_table
    oa.save(conn, "444", None, oa.parse_bookmakers(BOOKS))
    conn.commit()
    conn.close()
    monkeypatch.setattr(app_module, "upcoming_match_pairs", lambda limit=60: [
        {"match_id": "444", "kickoff": "2099-01-01T15:00:00+00:00", "league": "Premier League",
         "home_team": "Arsenal", "away_team": "Chelsea"},
        {"match_id": "555", "kickoff": "2099-01-01T15:00:00+00:00", "league": "Premier League",
         "home_team": "Everton", "away_team": "Fulham"},
    ])
    fx = {(f["match_id"], f["team"]): f for f in app_module.fixtures_from_upcoming()}

    home = fx[("444", "Arsenal")]
    assert home["back_odds"] == 2.15 and home["bookmaker"] == "William Hill"
    assert home["odds_estimated"] is False and home["lay_estimated"] is True
    opp = build_opportunity(home)
    assert opp["estimated_lay"] is True and opp["odds_estimated"] is False
    assert opp["lay_odds"] == home["lay_odds"]

    # no stored odds -> placeholder prices, clearly flagged
    other = fx[("555", "Everton")]
    assert other["bookmaker"] == "Estimated" and other["odds_estimated"] is True


def test_opportunities_window_keeps_next_24h_only(monkeypatch):
    from api import app as app_module
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(app_module, "upcoming_match_pairs", lambda limit=60: [
        {"match_id": "a", "kickoff": (now + timedelta(hours=2)).isoformat(), "league": "Premier League",
         "home_team": "Arsenal", "away_team": "Chelsea"},
        {"match_id": "b", "kickoff": (now + timedelta(hours=40)).isoformat(), "league": "Premier League",
         "home_team": "Everton", "away_team": "Fulham"},
    ])
    assert {f["match_id"] for f in app_module.fixtures_from_upcoming(hours=24)} == {"a"}
    assert {f["match_id"] for f in app_module.fixtures_from_upcoming()} == {"a", "b"}


def test_refresh_button_has_shared_cooldown_and_daily_budget(monkeypatch, tmp_path):
    import time
    from api import odds_refresh as orf

    calls = []

    def fake_refresh(hours, max_calls=200, skip_minutes=15, log=print):
        calls.append((hours, max_calls))
        return {"saved": 3, "calls": 5}

    monkeypatch.setattr(orf.odds_apisports, "refresh", fake_refresh)
    monkeypatch.setattr(orf, "LOCK_FILE", tmp_path / "odds.lock")
    orf._state.update(running=False, finished_at=None, last=None, error=None, day=None, calls_today=0)

    started, st = orf.start()
    assert started and st["reason"] == "started"
    for _ in range(50):
        if not orf._state["running"]:
            break
        time.sleep(0.02)
    assert calls == [(24, 200)]
    assert orf.status()["last"] == {"saved": 3, "calls": 5}

    started, st = orf.start()          # second press inside the cooldown
    assert not started and st["reason"] == "cooldown" and st["retry_after_s"] > 0
    assert len(calls) == 1

    orf._state.update(finished_at=None, calls_today=orf.DAILY_CALLS)  # budget spent
    started, st = orf.start()
    assert not started and st["reason"] == "daily_limit"


def test_refresh_endpoint_requires_pro(monkeypatch):
    from fastapi.testclient import TestClient
    from api import app as app_module
    with TestClient(app_module.app) as c:
        assert c.post("/odds/refresh").status_code in (401, 402)
