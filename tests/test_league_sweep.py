"""League sweep: stage-1 numbers from half-time / full-time scores, candidate filter."""

from scripts import league_sweep as ls


def fx(ht, ft):
    return {"score": {"halftime": {"home": ht[0], "away": ht[1]},
                      "fulltime": {"home": ft[0], "away": ft[1]}}}


def test_score_fixtures_counts_two_up_and_ht_collapses():
    s = ls.score_fixtures([
        fx((2, 0), (2, 2)),   # home 2 up at HT, fails to win
        fx((0, 0), (3, 1)),   # home 2 up only at FT
        fx((1, 0), (1, 0)),   # never 2 up
        fx((None, None), (1, 1)),  # no half-time score: skipped
    ])
    assert s["matches"] == 3
    assert abs(s["goals"] - (4 + 4 + 1) / 3) < 1e-9
    assert abs(s["up2"] - 100 * 2 / 6) < 1e-9
    assert abs(s["htfail"] - 100 * 1 / 6) < 1e-9


def test_candidates_need_league_events_and_odds():
    def item(i, name, typ="League", events=True, odds=True, current=False):
        # last season: events but (as api-sports reports) no odds; this season: odds flag
        seasons = [{"year": 2025, "current": current,
                    "coverage": {"fixtures": {"events": events}, "odds": False}},
                   {"year": 2026, "current": not current,
                    "coverage": {"fixtures": {"events": events}, "odds": odds}}]
        if current:
            seasons = seasons[:1]
            seasons[0]["coverage"]["odds"] = odds
        return {"league": {"id": i, "name": name, "type": typ}, "country": {"name": "X"},
                "seasons": seasons}
    why = {}
    cands = ls.candidates([
        item(1, "Good League"), item(2, "Some Cup", typ="Cup"), item(3, "No Events", events=False),
        item(4, "No Odds", odds=False), item(5, "Only Current", current=True), item(39, "Premier League"),
        item(6, "Liga U19"), item(7, "Women's League"),
    ], why)
    ids = {c["id"]: c for c in cands}
    assert set(ids) == {1, 39, 6, 7}
    assert ids[39]["ours"] and not ids[1]["ours"]
    assert ids[6]["kind"] == "youth" and ids[7]["kind"] == "women" and ids[1]["kind"] == "senior"
    assert cands[0]["id"] == 39  # benchmark leagues first
    assert all(c["season"] == 2025 for c in cands)  # the finished season, not the current
    assert why == {"cup / not a league": 1, "no finished season with goal events": 2,
                   "no odds this season": 1}


def test_ranked_filters_and_sorts():
    rows = [
        {"id": "1", "league": "A", "country": "X", "season": "2025", "ours": "0", "kind": "senior",
         "matches": "300", "goals": "2.9", "up2": "26.0", "htfail": "0.5"},
        {"id": "2", "league": "B", "country": "X", "season": "2025", "ours": "0", "kind": "women",
         "matches": "300", "goals": "3.5", "up2": "35.0", "htfail": "0.9"},
        {"id": "3", "league": "C", "country": "X", "season": "2025", "ours": "0", "kind": "senior",
         "matches": "50", "goals": "3.0", "up2": "40.0", "htfail": "1.0"},
        {"id": "4", "league": "D", "country": "X", "season": "2025", "ours": "1", "kind": "senior",
         "matches": "380", "goals": "2.7", "up2": "28.0", "htfail": "0.6"},
    ]
    out = ls.ranked(rows)
    assert [r["id"] for r in out] == ["4", "1"]          # women + tiny sample dropped
    assert [r["id"] for r in ls.ranked(rows, show_all=True)] == ["2", "4", "1"]


def test_kind_catches_spanish_womens_names():
    assert ls.kind_of("Liga MX Femenil") == "women"
    assert ls.kind_of("Primera División Femenina") == "women"
    assert ls.kind_of("Regionalliga - Nord") == "senior"


def test_top_ids_shows_requested_leagues(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ls, "OUT", tmp_path / "sweep.csv")
    base = {"country": "X", "season": "2025", "kind": "senior", "matches": "300",
            "goals": "3.0", "htfail": "0.8", "at": ""}
    for i, up2, ours in (("1", "30.0", "0"), ("2", "25.0", "0"), ("39", "20.0", "1")):
        ls.append_row({**base, "id": i, "league": f"L{i}", "ours": ours, "up2": up2})
    ls.top(ids=[2, 39, 999])
    out = capsys.readouterr().out
    assert "#2 " in out and "OURS" in out and "999" in out and "L1" not in out
