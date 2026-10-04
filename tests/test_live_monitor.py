"""Live monitor: api-sports fixture -> state, bet verdicts, shared caching."""

from api import live_monitor as lm


def _fx(fid, gh, ga, short="2H", elapsed=70, events=None, league=703):
    item = {"fixture": {"id": fid, "date": "2026-10-04T13:00:00+00:00",
                        "status": {"short": short, "elapsed": elapsed, "extra": None}},
            "league": {"id": league, "name": "Professional Development League"},
            "teams": {"home": {"id": 1, "name": "Fleetwood Town U21"},
                      "away": {"id": 2, "name": "Sheffield Wednesday U21"}},
            "goals": {"home": gh, "away": ga}}
    if events is not None:
        item["events"] = events
    return item


def _goal(minute, team_id):
    return {"type": "Goal", "detail": "Normal Goal", "time": {"elapsed": minute, "extra": None},
            "team": {"id": team_id}, "player": {"name": "x"}}


def test_parse_and_sides_use_goal_events():
    st = lm.parse_fixture(_fx(5, 2, 2, events=[_goal(2, 1), _goal(23, 1), _goal(60, 2), _goal(70, 2)]))
    assert st["phase"] == "live" and st["goals"] == [(2, 1), (23, 1), (60, 2), (70, 2)]
    home = lm.side_summary(st, 1)
    assert home["went_2up"] and home["two_up_minute"] == 23 and not home["winning"]
    away = lm.side_summary(st, 2)
    assert not away["went_2up"]


def test_score_only_when_events_missing_or_wrong():
    st = lm.parse_fixture(_fx(6, 3, 1))                       # no events at all
    assert st["goals"] is None and lm.side_summary(st, 1)["went_2up"]
    st = lm.parse_fixture(_fx(7, 2, 0, events=[_goal(10, 1)]))  # events don't match score
    assert st["goals"] is None


def test_bet_verdicts():
    bet = {"id": 1, "home_team": "Fleetwood Town U21", "away_team": "Sheffield Wednesday U21",
           "team": "Fleetwood Town U21", "league": "Professional Development League", "match_id": "5"}
    live = lm.parse_fixture(_fx(5, 2, 2, events=[_goal(2, 1), _goal(23, 1), _goal(60, 2), _goal(70, 2)]))
    assert lm.bet_view(bet, live)["verdict"] == "comeback_on"
    done = lm.parse_fixture(_fx(5, 3, 1, short="FT", elapsed=90,
                                events=[_goal(2, 1), _goal(23, 1), _goal(46, 1), _goal(85, 2)]))
    v = lm.bet_view(bet, done)
    assert v["verdict"] == "held" and v["turnaround_pct"] is None
    assert lm.bet_view(bet, None)["phase"] == "upcoming"


def test_shared_cache_one_call_per_ttl(monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append(params)
        if params.get("live") == "all":
            return {"response": [_fx(9, 2, 0, elapsed=30), _fx(10, 2, 0, league=999999)]}
        return {"response": [_fx(int(i), 1, 0) for i in params["ids"].split("-")]}

    monkeypatch.setattr(lm, "_get", fake_get)
    monkeypatch.setattr(lm, "_fixtures", {})
    monkeypatch.setattr(lm, "_live_all", {"ts": 0.0, "states": []})
    bets = [{"id": 1, "match_id": "5", "kickoff": None, "home_team": "Fleetwood Town U21",
             "away_team": "Sheffield Wednesday U21", "team": "Fleetwood Town U21", "league": "L"}]
    out1 = lm.monitor(bets, now=1000.0)
    out2 = lm.monitor(bets, now=1030.0)            # within the TTL: no new calls
    assert len(calls) == 2
    assert out1["my_bets"][0]["phase"] == "live" and out2["my_bets"][0]["team_goals"] == 1
    assert [g["fixture_id"] for g in out1["live_now"]] == ["9"]   # other leagues dropped
    lm.monitor(bets, now=1061.0)
    assert len(calls) == 4
