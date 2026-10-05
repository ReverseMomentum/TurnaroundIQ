"""Scorecard: pre-kick-off predictions logged once per side, then matched to results."""

from datetime import datetime, timedelta, timezone

from database import get_db
from models import scorecard as sc


def _reset():
    conn = get_db()
    conn.execute("DROP TABLE IF EXISTS prediction_log")
    conn.execute("DROP TABLE IF EXISTS match_results")
    conn.execute("""CREATE TABLE match_results (id INTEGER PRIMARY KEY, match_id TEXT, league TEXT,
        home_team TEXT, away_team TEXT, final_home INTEGER, final_away INTEGER,
        home_2up INTEGER, away_2up INTEGER, processed_at TEXT)""")
    conn.commit()
    conn.close()


def _opp(mid, team, home, away, fta, ko):
    return {"match_id": mid, "team": team, "home_team": home, "away_team": away, "league": "L",
            "kickoff": ko.isoformat(), "fta_pct": fta, "two_up_pct": 25.0, "turnaround_pct": 8.0,
            "model_version": "V6"}


def test_log_upserts_until_kickoff_and_report_scores_results():
    _reset()
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=2)
    assert sc.log_predictions([_opp("1", "A", "A", "B", 2.0, soon), _opp("1", "B", "A", "B", 1.5, soon)]) == 2
    o = _opp("1", "A", "A", "B", 3.2, soon)
    o.update(back_odds=2.05, exchange={"back": 2.96, "back_size": 55, "lay": 3.2, "lay_size": 187,
                                       "updated_at": "2026-10-05T12:30:00+00:00"})
    sc.log_predictions([o])                                                # later update wins
    sc.log_predictions([_opp("1", "A", "A", "B", 3.2, soon)])              # no prices: keeps the last ones
    conn = get_db()
    assert conn.execute("SELECT book_back, exch_lay, exch_lay_size FROM prediction_log WHERE team='A'"
                        ).fetchone() == (2.05, 3.2, 187)
    conn.close()
    started = now - timedelta(minutes=5)
    assert sc.log_predictions([_opp("2", "C", "C", "D", 2.0, started)]) == 0  # never after kick-off

    conn = get_db()
    conn.execute("UPDATE prediction_log SET kickoff = ?", ((now - timedelta(days=1)).isoformat(),))
    # A went 2 up and drew: FTA for A; B did not
    conn.execute("INSERT INTO match_results (match_id, final_home, final_away, home_2up, away_2up) "
                 "VALUES ('1', 2, 2, 1, 0)")
    conn.commit()
    conn.close()

    scored, pending = sc.scored_rows(days=30)
    assert sorted(scored) == [(1.5, 0, "L"), (3.2, 1, "L")]
    assert pending == 0
    s = sc.summarise(scored)
    assert s["sides"] == 2 and s["actual"] == 50.0 and s["picks_n"] == 1 and s["picks_actual"] == 100.0
    assert sc.report(30)["sides"] == 2


def test_report_with_nothing_scored():
    _reset()
    assert sc.report(30) is None
