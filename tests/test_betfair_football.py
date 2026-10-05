"""Betfair football: matching Betfair markets to our fixtures, prices per side."""

from datetime import datetime, timedelta, timezone

from collectors import betfair_football as bff


def test_names_match_across_spellings():
    assert bff.name_score("Sheff Utd U21", "Sheffield United U21") > 0.8
    assert bff.name_score("Man City", "Manchester City") > 0.8
    assert bff.name_score("Bolton Res", "Bolton Wanderers Res") >= bff.MIN_SIDE_SCORE
    assert bff.name_score("Sheff Wed U21", "Sheffield United U21") < bff.MIN_SIDE_SCORE
    assert bff.name_score("Man Utd", "Manchester City") < bff.MIN_SIDE_SCORE
    assert bff.name_score("Bayern Munich", "Bayern München") > 0.8
    assert bff.name_score("Fleetwood", "Fleetwood Town") >= bff.MIN_SIDE_SCORE
    assert bff.name_score("Wolves", "Wolverhampton Wanderers") >= bff.MIN_SIDE_SCORE
    assert bff.is_youth("Fleetwood U21") and bff.is_youth("Jong PSV") and not bff.is_youth("Fleetwood Town")


def _market(mid, event, start, runners=("H", "A", "The Draw")):
    return {"marketId": mid, "event": {"name": event}, "marketStartTime": start.isoformat().replace("+00:00", "Z"),
            "runners": [{"selectionId": i + 1, "runnerName": n, "sortPriority": i + 1} for i, n in enumerate(runners)]}


def test_match_markets_needs_time_names_and_same_age_group():
    ko = datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc)
    fixtures = [{"match_id": 1, "kickoff": ko, "home": "Fleetwood Town U21", "away": "Sheffield Wednesday U21"},
                {"match_id": 2, "kickoff": ko, "home": "Fleetwood Town", "away": "Sheffield Wednesday"}]
    markets = [_market("1.1", "Fleetwood U21 v Sheff Wed U21", ko),
               _market("1.2", "Fleetwood v Sheff Wed", ko + timedelta(minutes=5)),
               _market("1.3", "Fleetwood U21 v Sheff Wed U21", ko + timedelta(hours=2))]
    paired = bff.match_markets(markets, fixtures)
    assert paired["1"]["marketId"] == "1.1"      # youth only matches youth
    assert paired["2"]["marketId"] == "1.2"


def test_side_prices_and_app_prefers_betfair_lay():
    m = _market("1.1", "A v B", datetime.now(timezone.utc))
    book = {"runners": [
        {"selectionId": 1, "status": "ACTIVE", "ex": {"availableToBack": [{"price": 2.96, "size": 55}],
                                                      "availableToLay": [{"price": 3.2, "size": 187}]}},
        {"selectionId": 2, "status": "ACTIVE", "ex": {"availableToBack": [{"price": 2.24, "size": 230}],
                                                      "availableToLay": [{"price": 2.34, "size": 11}]}}]}
    p = bff.side_prices(m, book)
    assert p["home"] == (2.96, 55, 3.2, 187) and p["away"] == (2.24, 230, 2.34, 11)

    from api import app as app_module
    xrow = {"home_back": 2.96, "home_back_size": 55, "home_lay": 3.2, "home_lay_size": 187,
            "updated_at": "2026-10-05T12:00:00+00:00"}
    row = {"home_back": 2.05, "home_book": "Bet365", "home_lay_est": 2.30, "updated_at": "x", "books_json": "{}"}
    out = app_module._with_prices({"team": "A"}, row, True, None, xrow)
    assert out["lay_odds"] == 3.2 and out["lay_estimated"] is False
    assert out["exchange"]["lay_size"] == 187 and out["back_odds"] == 2.05
    est = app_module._with_prices({"team": "A"}, row, True, None, None)
    assert est["lay_odds"] == 2.30 and est["lay_estimated"] is True and "exchange" not in est
