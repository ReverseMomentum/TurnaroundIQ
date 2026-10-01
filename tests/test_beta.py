"""Free beta switch: signed-in accounts get Pro until BETA_FREE_UNTIL, optionally capped."""

from datetime import datetime, timezone

import pytest

from api import auth
from billing import beta
from database import get_db


@pytest.fixture
def users():
    auth.ensure_auth_tables()
    conn = get_db()
    conn.execute("DELETE FROM users")
    for i in range(3):
        conn.execute("INSERT INTO users (id, email, created_at) VALUES (?,?,?)",
                     (f"u_beta{i}", f"b{i}@example.com", f"2026-10-0{i + 1}T10:00:00+00:00"))
    conn.commit()
    conn.close()
    yield


def test_no_beta_by_default(monkeypatch, users):
    monkeypatch.delenv("BETA_FREE_UNTIL", raising=False)
    assert not beta.covers("u_beta0")
    assert beta.info("u_beta0")["until"] is None


def test_beta_ends_at_uk_midnight_after_last_day(monkeypatch, users):
    monkeypatch.setenv("BETA_FREE_UNTIL", "2026-11-30")
    assert beta.beta_ends_at().isoformat() == "2026-12-01T00:00:00+00:00"  # GMT in winter
    inside = datetime(2026, 11, 30, 23, 59, tzinfo=timezone.utc)
    after = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
    assert beta.covers("u_beta0", now=inside)
    assert not beta.covers("u_beta0", now=after)


def test_only_signed_in_accounts(monkeypatch, users):
    monkeypatch.setenv("BETA_FREE_UNTIL", "2099-01-01")
    assert beta.covers("u_beta1")
    assert not beta.covers("$RCAnonymousID:abc")
    assert not beta.covers("")


def test_cap_admits_earliest_signups(monkeypatch, users):
    monkeypatch.setenv("BETA_FREE_UNTIL", "2099-01-01")
    monkeypatch.setenv("BETA_MAX_USERS", "2")
    assert beta.covers("u_beta0") and beta.covers("u_beta1")
    assert not beta.covers("u_beta2")
    assert not beta.covers("u_unknown")


def test_require_pro_and_me_during_beta(monkeypatch, users):
    from fastapi import HTTPException
    from api import app as app_module
    monkeypatch.setattr(app_module, "user_from_auth", lambda a: "u_beta0")
    monkeypatch.setattr(app_module, "is_entitled", lambda uid, refresh=False: False)
    monkeypatch.setenv("BETA_FREE_UNTIL", "2026-01-01")  # over
    with pytest.raises(HTTPException) as exc:
        app_module.require_pro("Bearer x")
    assert exc.value.status_code == 402

    monkeypatch.setenv("BETA_FREE_UNTIL", "2099-01-01")
    monkeypatch.setenv("BETA_FOUNDER_PRICE", "£6.99")
    monkeypatch.setenv("RC_WEB_PURCHASE_LINK", "https://pay.example/link")
    assert app_module.require_pro("Bearer x") == "u_beta0"
    me = app_module.me("Bearer x")
    assert me["entitled"] is True and me["paid"] is False
    assert me["status"] == "beta"
    assert me["beta"]["founder_price"] == "£6.99"
    assert me["purchase_url"].endswith("/u_beta0")  # beta users can still subscribe
