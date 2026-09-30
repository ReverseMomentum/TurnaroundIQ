"""Email-code sign-in for the web app."""

import pytest


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from api import app as app_module, auth

    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    sent = {}
    monkeypatch.setattr(auth, "send_code_email", lambda email, code: sent.__setitem__(email, code))
    monkeypatch.setenv("RC_WEB_PURCHASE_LINK", "https://pay.rev.cat/testlink")
    auth.ensure_auth_tables()
    from database import get_db
    conn = get_db()
    for t in ("users", "login_codes", "sessions"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()
    with TestClient(app_module.app) as c:
        yield c, sent


def sign_in(c, sent, email="Punter@Example.com"):
    assert c.post("/auth/start", json={"email": email}).status_code == 200
    code = sent[email.lower()]
    r = c.post("/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200
    return r.json()


def test_sign_in_and_me(client):
    c, sent = client
    s = sign_in(c, sent)
    assert s["token"].startswith("s_") and s["user_id"].startswith("u_")
    me = c.get("/me", headers={"Authorization": "Bearer " + s["token"]}).json()
    assert me["app_user_id"] == s["user_id"]
    assert me["email"] == "punter@example.com"
    assert me["entitled"] is False
    assert me["purchase_url"] == "https://pay.rev.cat/testlink/" + s["user_id"]


def test_same_email_same_account(client):
    c, sent = client
    a = sign_in(c, sent)
    b = sign_in(c, sent)
    assert a["user_id"] == b["user_id"] and a["token"] != b["token"]


def test_raw_account_id_is_refused(client):
    c, sent = client
    s = sign_in(c, sent)
    r = c.get("/me", headers={"Authorization": "Bearer " + s["user_id"]})
    assert r.status_code == 401


def test_wrong_code_and_lockout(client):
    c, sent = client
    c.post("/auth/start", json={"email": "a@b.co"})
    for _ in range(5):
        assert c.post("/auth/verify", json={"email": "a@b.co", "code": "000000"}).status_code == 400
    # even the right code is dead after too many attempts
    r = c.post("/auth/verify", json={"email": "a@b.co", "code": sent["a@b.co"]})
    assert r.status_code == 400


def test_code_is_single_use(client):
    c, sent = client
    c.post("/auth/start", json={"email": "x@y.io"})
    code = sent["x@y.io"]
    assert c.post("/auth/verify", json={"email": "x@y.io", "code": code}).status_code == 200
    assert c.post("/auth/verify", json={"email": "x@y.io", "code": code}).status_code == 400


def test_rate_limit(client):
    c, _ = client
    for _ in range(5):
        assert c.post("/auth/start", json={"email": "r@l.io"}).status_code == 200
    assert c.post("/auth/start", json={"email": "r@l.io"}).status_code == 429


def test_logout_kills_session(client):
    c, sent = client
    s = sign_in(c, sent)
    h = {"Authorization": "Bearer " + s["token"]}
    assert c.post("/auth/logout", headers=h).status_code == 200
    assert c.get("/me", headers=h).status_code == 401


def test_bad_email(client):
    c, _ = client
    assert c.post("/auth/start", json={"email": "nope"}).status_code == 400


def test_native_rc_ids_still_work(client):
    c, _ = client
    r = c.get("/me", headers={"Authorization": "Bearer $RCAnonymousID:abc123"})
    assert r.status_code == 200 and r.json()["purchase_url"] is None


def test_delete_account_erases_data(client):
    c, sent = client
    s = sign_in(c, sent)
    h = {"Authorization": "Bearer " + s["token"]}
    c.patch("/me/prefs", headers=h, json={"default_stake": 25})
    assert c.request("DELETE", "/me", headers=h).json() == {"deleted": True}
    assert c.get("/me", headers=h).status_code == 401
    from database import get_db
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (s["user_id"],)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_prefs WHERE app_user_id = ?", (s["user_id"],)).fetchone()[0] == 0
    conn.close()
    # signing in again with the same email creates a fresh, empty account
    again = sign_in(c, sent)
    assert again["user_id"] != s["user_id"]
