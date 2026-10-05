"""/me answers from the stored subscriber row instead of waiting on RevenueCat."""

from datetime import datetime, timedelta, timezone

from billing import revenuecat as rc
from database import get_db


def _set_updated(user, when):
    conn = get_db()
    conn.execute("UPDATE subscribers SET updated_at = ? WHERE app_user_id = ?", (when.isoformat(), user))
    conn.commit()
    conn.close()


def test_entitled_quick(monkeypatch):
    calls = []

    def fake_fetch(user):
        calls.append(user)
        return {"subscriber": {"entitlements": {}}}

    monkeypatch.setattr(rc, "fetch_subscriber", fake_fetch)
    started = []
    monkeypatch.setattr(rc, "_refresh_in_background", lambda u: started.append(u))

    # unknown user: must look up live
    assert rc.entitled_quick("u_speed_new") is False
    assert calls == ["u_speed_new"]

    # known free user, recent row: no lookup at all
    assert rc.entitled_quick("u_speed_new") is False
    assert calls == ["u_speed_new"] and started == []

    # stale row: answer straight away, refresh in the background
    _set_updated("u_speed_new", datetime.now(timezone.utc) - timedelta(hours=1))
    assert rc.entitled_quick("u_speed_new") is False
    assert calls == ["u_speed_new"] and started == ["u_speed_new"]

    # just bought: wait for RevenueCat
    rc.entitled_quick("u_speed_new", fresh=True)
    assert calls == ["u_speed_new", "u_speed_new"]


def test_paid_user_served_from_row(monkeypatch):
    rc.upsert_subscriber("u_speed_paid", True, expires_at=(datetime.now(timezone.utc) + timedelta(days=20)).isoformat())
    rc._looked_up.add("u_speed_paid")
    monkeypatch.setattr(rc, "fetch_subscriber", lambda u: (_ for _ in ()).throw(AssertionError("no live call")))
    assert rc.entitled_quick("u_speed_paid") is True
