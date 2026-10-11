"""In-play Betfair logger and the lay-the-draw report built on it."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from collectors import betfair_football, betfair_inplay
from database import get_db

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import inplay_drift_report as rep  # noqa: E402

NOW = datetime(2026, 10, 11, 15, 30, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, inplay=True):
        self.inplay, self.calls = inplay, []

    def call(self, method, params):
        self.calls.append(method)
        if method == "listMarketCatalogue":
            return [{"marketId": m, "runners": [{"selectionId": 1, "sortPriority": 1},
                                                {"selectionId": 2, "sortPriority": 2},
                                                {"selectionId": 58805, "sortPriority": 3}]}
                    for m in params["filter"]["marketIds"]]
        if method == "listMarketBook":
            def r(sel, b, lay):
                return {"selectionId": sel, "status": "ACTIVE",
                        "ex": {"availableToBack": [{"price": b, "size": 50}], "availableToLay": [{"price": lay, "size": 60}]}}
            return [{"marketId": m, "status": "OPEN", "inplay": self.inplay, "totalMatched": 1000,
                     "runners": [r(1, 2.0, 2.02), r(2, 4.5, 4.6), r(58805, 3.6, 3.65)]}
                    for m in params["marketIds"]]
        raise AssertionError(method)


def _games(rows):
    conn = get_db()
    betfair_football.ensure_table(conn)
    conn.execute("DELETE FROM exchange_odds")
    for mid, market, ko in rows:
        conn.execute("INSERT INTO exchange_odds (match_id, market_id, kickoff, updated_at) VALUES (?,?,?,?)",
                     (mid, market, ko, NOW.isoformat()))
    betfair_inplay.ensure_tables(conn)
    conn.execute("DELETE FROM inplay_prices")
    conn.commit()
    conn.close()


def test_logs_only_games_in_the_window():
    _games([("101", "1.1", (NOW - timedelta(minutes=30)).isoformat()),      # in play
            ("102", "1.2", (NOW + timedelta(minutes=5)).isoformat()),       # about to start
            ("103", "1.3", (NOW + timedelta(hours=3)).isoformat()),         # later: ignored
            ("104", "1.4", (NOW - timedelta(hours=4)).isoformat())])        # finished: ignored
    client = FakeClient()
    n = betfair_inplay.run(client=client, now=NOW, scores={"101": (31, 1, 0, "1H")}, log=lambda *_: None)
    assert n == 2
    conn = get_db()
    rows = conn.execute("SELECT match_id, minute, home_goals, draw_back, draw_lay, draw_lay_size, home_back "
                        "FROM inplay_prices ORDER BY match_id").fetchall()
    conn.close()
    assert rows[0] == ("101", 31, 1, 3.6, 3.65, 60, 2.0)
    assert rows[1][0] == "102" and rows[1][1] is None


def test_nothing_called_without_games():
    _games([])
    client = FakeClient()
    assert betfair_inplay.run(client=client, now=NOW, scores={}, log=lambda *_: None) == 0
    assert client.calls == []


def _snaps(goal_minute=None, draw_after=5.5, final=(1, 0)):
    s = [{"inplay": 0, "minute": None, "hg": None, "ag": None, "hb": 2.0, "hl": 2.02,
          "db": 3.5, "dl": 3.55, "ab": 4.5, "al": 4.6}]
    for minute in range(1, 91):
        scored = goal_minute is not None and minute >= goal_minute
        hg, ag = (final if minute == 90 else ((1, 0) if scored else (0, 0)))
        db = draw_after if scored else 3.5 - minute * 0.02
        s.append({"inplay": 1, "minute": minute, "hg": hg, "ag": ag, "hb": 2.0, "hl": 2.02,
                  "db": db, "dl": db + 0.05, "ab": 4.5, "al": 4.6})
    return s


def test_trade_after_goal_and_exit_at_nil_nil():
    g = rep.evaluate(_snaps(goal_minute=20), commission=0.0)
    assert g["kind"] == "goal" and g["minute"] == 20 and g["back"] == 5.5
    assert g["trade"] == pytest.approx(10 - 10 * 3.55 / 5.5)
    assert g["hold"] == 10 and g["scorer_fav"] is True
    z = rep.evaluate(_snaps(goal_minute=None, final=(0, 0)), commission=0.0)
    assert z["kind"] == "exit00" and z["trade"] < 0 and z["draw"] == 1
    assert rep.evaluate(_snaps(goal_minute=20)[:5]) is None          # too little logged
