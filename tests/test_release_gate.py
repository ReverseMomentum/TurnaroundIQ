"""
Release-gate safety tests: backups, health, entitlement, fixture freshness.

    python -m pytest tests -q
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import database
from ops import backup, health


def _seed(n_results=3):
    Path(database.DB_NAME).unlink(missing_ok=True)
    conn = sqlite3.connect(database.DB_NAME)
    conn.execute("CREATE TABLE match_results (id INTEGER PRIMARY KEY, processed_at TEXT)")
    conn.execute("CREATE TABLE team_stats (team TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE training_data (id INTEGER PRIMARY KEY)")
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(n_results):
        conn.execute("INSERT INTO match_results (processed_at) VALUES (?)", (now,))
    conn.execute("INSERT INTO team_stats VALUES ('Arsenal')")
    conn.execute("INSERT INTO training_data DEFAULT VALUES")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def clean_backups():
    for f in backup.list_backups():
        f.unlink()
    yield


def test_db_path_is_absolute():
    assert Path(database.DB_NAME).is_absolute()


def test_backup_and_restore_roundtrip():
    _seed(3)
    saved = backup.backup_db("test")
    assert saved.is_file()
    assert backup.row_counts(saved)["match_results"] == 3

    # Simulate the wiped-DB incident, then restore.
    conn = sqlite3.connect(database.DB_NAME)
    conn.execute("DELETE FROM match_results")
    conn.commit()
    conn.close()
    backup.restore_db(saved)
    assert backup.row_counts(database.DB_NAME)["match_results"] == 3
    # Restore keeps a copy of what it replaced.
    assert any("pre-restore" in f.name for f in backup.list_backups())


def test_empty_backup_never_prunes_good_ones(monkeypatch):
    _seed(3)
    monkeypatch.setattr(backup, "BACKUP_KEEP", 1)
    good = backup.backup_db("good")
    _seed(0)
    backup.backup_db("empty")
    assert good.is_file(), "empty DB backup rotated out the last good copy"


def test_backup_missing_db_raises():
    Path(database.DB_NAME).unlink(missing_ok=True)
    with pytest.raises(backup.BackupError):
        backup.backup_db("x")


def test_health_critical_on_empty_db():
    _seed(0)
    report = health.check()
    assert "match_results_empty" in report["critical"]
    assert report["status"] == "critical"


def test_health_reports_counts_and_missing_backup():
    _seed(2)
    report = health.check()
    assert report["row_counts"]["match_results"] == 2
    assert "no_backups" in report["warnings"]
    assert "match_results_empty" not in report["critical"]


def test_webhook_auth():
    from billing.revenuecat import webhook_auth_ok
    assert webhook_auth_ok("test-webhook-secret")
    assert webhook_auth_ok("Bearer test-webhook-secret")
    assert not webhook_auth_ok("wrong")
    assert not webhook_auth_ok(None)


def _webhook(kind, user, expires_in_days=30):
    exp = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    return {"event": {
        "type": kind,
        "app_user_id": user,
        "entitlement_ids": ["pro"],
        "expiration_at_ms": int(exp.timestamp() * 1000),
        "environment": "SANDBOX",
    }}


def test_entitlement_lifecycle_via_webhooks():
    """Purchase → Pro, cancellation keeps access until expiry, expiry → paywall."""
    from billing import revenuecat as rc
    user = "rc_test_user"
    rc.ensure_tables()
    assert not rc.is_entitled(user)

    rc.apply_webhook(_webhook("INITIAL_PURCHASE", user))
    assert rc.is_entitled(user)

    rc.apply_webhook(_webhook("CANCELLATION", user))
    assert rc.is_entitled(user)

    rc.apply_webhook(_webhook("EXPIRATION", user, expires_in_days=-1))
    assert not rc.is_entitled(user)


def test_manual_grant_survives_revenuecat_lookup(monkeypatch):
    """A grant_pro comp must not be wiped when RevenueCat (which never saw it) says 'no purchase'."""
    from billing import revenuecat as rc
    user = "u_comp_tester"
    exp = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    rc.upsert_subscriber(user, True, entitlement="pro", expires_at=exp, status="active",
                         product_id="comp", environment="MANUAL", last_event="MANUAL_GRANT")
    monkeypatch.setattr(rc, "fetch_subscriber", lambda uid: {"subscriber": {"entitlements": {}}})
    assert rc.is_entitled(user, refresh=True)
    assert rc.get_subscriber_row(user)["environment"] == "MANUAL"

    # an unrelated real-subscription expiry doesn't cancel the comp either
    rc.apply_webhook(_webhook("EXPIRATION", user, expires_in_days=-1))
    assert rc.is_entitled(user, refresh=True)

    # an expired comp falls back to what RevenueCat says
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rc.upsert_subscriber(user, True, entitlement="pro", expires_at=past, status="active",
                         product_id="comp", environment="MANUAL", last_event="MANUAL_GRANT")
    assert not rc.is_entitled(user, refresh=True)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api import app as app_module
    _seed(3)
    app_module._upcoming_cache = {"ts": 0.0, "pairs": []}
    with TestClient(app_module.app) as c:
        yield c, app_module


def test_health_endpoint_503_when_db_empty(client):
    c, _ = client
    _seed(0)
    r = c.get("/health")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert "match_results_empty" in r.json()["critical"]


def test_opportunities_requires_auth_and_pro(client):
    c, _ = client
    assert c.get("/opportunities").status_code == 401
    r = c.get("/opportunities", headers={"Authorization": "Bearer free_user"})
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "SUBSCRIPTION_REQUIRED"


def test_no_finished_matches_served_as_upcoming(client):
    _, app_module = client
    # API-Football unavailable (no key) and no cache: must be empty, not old results.
    assert app_module.upcoming_match_pairs() == []
    assert app_module.fixture_meta()["fixture_source"] == "unavailable"


def test_cached_fixtures_drop_kicked_off_games(client):
    _, app_module = client
    now = datetime.now(timezone.utc)
    app_module._upcoming_cache = {"ts": 0.0, "pairs": [
        {"kickoff": (now - timedelta(hours=1)).isoformat(), "home_team": "A", "away_team": "B"},
        {"kickoff": (now + timedelta(hours=5)).isoformat(), "home_team": "C", "away_team": "D"},
    ]}
    pairs = app_module.upcoming_match_pairs()
    assert [p["home_team"] for p in pairs] == ["C"]
    assert app_module.fixture_meta()["fixture_source"] == "cached-upcoming"


def test_mismatch_hidden_by_default(client):
    c, _ = client
    r = c.get("/features/mismatch", headers={"Authorization": "Bearer x"})
    assert r.status_code == 404


def test_restore_drill_passes_and_leaves_live_untouched():
    _seed(3)
    before = backup.row_counts(database.DB_NAME)
    assert backup.drill() is True
    assert backup.row_counts(database.DB_NAME) == before


def test_paper_fta_bet_uses_matched_bet_maths():
    """A miss costs the qualifying loss (~£1-2), not the whole stake; % is never x100."""
    from api import tracked
    ql, fta = tracked.matched_bet_outcomes(40, 2.1, 2.2, 2.0)
    assert -3 < ql < 0 and fta > 60
    assert tracked.compute_profit("no_fta", 40, 2.1, 2.0, lay_odds=2.2) == ql
    assert tracked.compute_profit("fta", 40, 2.1, 2.0, lay_odds=2.2) == fta
    exp = tracked._expected_profit(40, 2.1, 1.2, 2.0, lay_odds=2.2)  # 1.2% full event
    assert exp == round(fta * 0.012 - abs(ql) * 0.988, 2)


def test_tracked_bet_edit_and_delete():
    from api import tracked as store
    user = "u_editor"
    bet = store.create_tracked(user, {"home_team": "Arsenal", "away_team": "Chelsea", "team": "Arsenal",
                                      "back_odds": 2.0, "lay_odds": 2.1, "stake": 40, "commission": 2,
                                      "fta_pct": 3.0})
    edited = store.update_tracked(user, bet["id"], {"stake": 100, "back_odds": 2.2, "bogus": 1})
    assert edited["stake"] == 100 and edited["back_odds"] == 2.2 and edited["lay_odds"] == 2.1
    assert edited["lay_stake"] == round(2.2 * 100 / (2.1 - 0.02), 2)
    assert edited["expected_profit"] != bet["expected_profit"]

    # settled bets keep their result; profit follows the corrected prices
    store.settle_tracked(user, bet["id"], "no_fta")
    before = [b for b in store.list_tracked(user) if b["id"] == bet["id"]][0]["actual_profit"]
    after = store.update_tracked(user, bet["id"], {"lay_odds": 2.4})
    assert after["status"] == "settled" and after["result"] == "no_fta"
    assert after["actual_profit"] != before

    assert store.update_tracked("someone_else", bet["id"], {"stake": 1}) is None
    assert not store.delete_tracked("someone_else", bet["id"])
    assert store.delete_tracked(user, bet["id"])
    assert all(b["id"] != bet["id"] for b in store.list_tracked(user))
