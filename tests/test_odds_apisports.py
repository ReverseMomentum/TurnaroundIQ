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


def test_refresh_endpoint_requires_pro():
    # call the endpoint directly: a TestClient would start the app's background
    # model warm-up thread, which can hold the DB while later tests restore it
    from fastapi import HTTPException
    from api import app as app_module
    with pytest.raises(HTTPException) as exc:
        app_module.refresh_odds(authorization=None)
    assert exc.value.status_code in (401, 402)


def test_best_price_respects_my_bookmakers(fresh_table):
    conn = fresh_table
    oa.save(conn, "777", None, oa.parse_bookmakers(BOOKS))
    conn.commit()
    conn.close()
    row = oa.load_odds(["777"])["777"]
    # any UK book: William Hill 2.15 is best for home
    assert oa.side_prices(row, True)[:2] == (2.15, "William Hill")
    # banned from William Hill -> best of the rest
    assert oa.side_prices(row, True, ["Bet365", "Paddy Power"])[:2] == (2.10, "Bet365")
    # case/spacing-insensitive names; non-UK books never count
    assert oa.side_prices(row, True, ["bet 365"])[:2] == (2.10, "Bet365")
    assert oa.side_prices(row, True, ["1xBet"]) is None
    assert [b for b, _ in oa.book_prices(row, True)] == ["William Hill", "Bet365"]


def test_available_bookmakers_lists_uk_books_seen(fresh_table):
    conn = fresh_table
    oa.save(conn, "888", None, oa.parse_bookmakers(BOOKS))
    conn.commit()
    conn.close()
    names, priced = oa.available_bookmakers()
    assert priced == ["Bet365", "William Hill"]
    assert names[:2] == ["Bet365", "William Hill"]  # priced first
    assert "Paddy Power" in names and "Sky Bet" in names  # every UK book is offered
    assert len(names) == len({n.lower() for n in names})  # no duplicates


def test_opportunities_use_saved_bookmakers(fresh_table, monkeypatch):
    from api import app as app_module
    from billing import revenuecat as rc

    conn = fresh_table
    oa.save(conn, "999", None, oa.parse_bookmakers(BOOKS))
    conn.commit()
    conn.close()
    monkeypatch.setattr(app_module, "upcoming_match_pairs", lambda limit=60: [
        {"match_id": "999", "kickoff": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
         "league": "Premier League", "home_team": "Arsenal", "away_team": "Chelsea"},
    ])
    saved = rc.save_prefs("u_books", {"bookmakers": ["Bet365", "  ", 123]})
    assert saved["bookmakers"] == ["Bet365", "123"]

    fx = app_module.fixtures_from_upcoming(hours=24, bookmakers=saved["bookmakers"])
    home = next(f for f in fx if f["team"] == "Arsenal")
    assert (home["bookmaker"], home["back_odds"]) == ("Bet365", 2.10)
    assert [p["bookmaker"] for p in home["back_prices"]] == ["Bet365"]

    # none of my books price it -> placeholder odds, clearly flagged
    fx = app_module.fixtures_from_upcoming(hours=24, bookmakers=["Betfred"])
    home = next(f for f in fx if f["team"] == "Arsenal")
    assert home["odds_estimated"] is True and home["not_at_my_books"] is True


def test_feature_pages_24h_window_and_score_floor(monkeypatch):
    from api import app as app_module
    now = datetime.now(timezone.utc)
    pairs = [
        {"match_id": "s", "kickoff": (now + timedelta(hours=3)).isoformat(), "league": "L",
         "home_team": "A", "away_team": "B"},
        {"match_id": "t", "kickoff": (now + timedelta(hours=5)).isoformat(), "league": "L",
         "home_team": "C", "away_team": "D"},
        {"match_id": "l", "kickoff": (now + timedelta(hours=40)).isoformat(), "league": "L",
         "home_team": "E", "away_team": "F"},
    ]
    monkeypatch.setattr(app_module, "upcoming_match_pairs", lambda limit=60: pairs)
    monkeypatch.setattr(app_module, "require_pro", lambda auth: "u_x")
    scores = {"s": 72, "t": 31, "l": 90}
    monkeypatch.setattr(app_module, "rank_early_goal_matches",
                        lambda ps: [{"match_id": p["match_id"], "hunter_score": scores[p["match_id"]]} for p in ps])
    monkeypatch.setattr(app_module, "rank_chaos_matches",
                        lambda ps: [{"match_id": p["match_id"], "chaos_index": scores[p["match_id"]]} for p in ps])

    early = app_module.early_goal_feature(authorization="x", limit=50, hours=24, min_score=40)
    assert [m["match_id"] for m in early["matches"]] == ["s"]  # 40h game and 31/100 hidden
    chaos = app_module.chaos_feature(authorization="x", limit=50, hours=24, min_score=40)
    assert [m["match_id"] for m in chaos["matches"]] == ["s"]
    # old behaviour without the params is unchanged
    assert len(app_module.early_goal_feature(authorization="x", limit=50)["matches"]) == 3


def test_over_under_parsed_prefers_pinnacle_and_is_stored(fresh_table):
    def ou_bk(name, over, under):
        return {"name": name, "bets": [{"id": 5, "name": "Goals Over/Under", "values": [
            {"value": "Over 1.5", "odd": "1.3"}, {"value": "Over 2.5", "odd": str(over)},
            {"value": "Under 2.5", "odd": str(under)}]}]}
    books = [ou_bk("Bet365", 1.90, 1.90), ou_bk("Pinnacle", 1.85, 2.02), ou_bk("1xBet", 2.0, 1.8)]
    assert oa.parse_over_under(books) == (1.85, 2.02)
    assert oa.parse_over_under(books[:1] + books[2:]) == (1.95, 1.85)  # median without Pinnacle
    assert oa.parse_over_under([]) == (None, None)
    oa.save(fresh_table, "ou1", None, oa.parse_bookmakers(BOOKS), oa.parse_over_under(books))
    fresh_table.commit()
    fresh_table.close()
    row = oa.load_odds(["ou1"])["ou1"]
    assert (row["over25"], row["under25"]) == (1.85, 2.02)
