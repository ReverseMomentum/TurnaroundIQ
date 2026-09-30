"""
Email sign-in for the web app (no passwords).

    POST /auth/start   {email}        -> emails a 6-digit code (always 200)
    POST /auth/verify  {email, code}  -> {token, user_id}
    POST /auth/logout                 -> ends the session

The session token ("s_…") is sent as `Authorization: Bearer <token>` and is
resolved server-side to the account id ("u_…"), which is also the RevenueCat
app_user_id used by the web purchase link and webhooks. Raw "u_" ids are never
accepted as bearer tokens, so knowing someone's id doesn't grant their access.

Env:
  AUTH_SECRET            long random string (hashing codes/tokens) — required
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM   — email sending
  AUTH_DEV_LOG_CODES=1   print codes to the log instead of emailing (testing only)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from database import get_db

CODE_TTL_MIN = 10
CODE_MAX_ATTEMPTS = 5
CODES_PER_EMAIL_PER_HOUR = 5
CODES_PER_IP_PER_HOUR = 20
SESSION_DAYS = 90
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _secret():
    s = os.environ.get("AUTH_SECRET", "").strip()
    if not s:
        raise AuthError(503, "Sign-in is not configured (AUTH_SECRET missing)")
    return s.encode()


def _h(value: str) -> str:
    return hmac.new(_secret(), value.encode(), hashlib.sha256).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def ensure_auth_tables():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL, code_hash TEXT NOT NULL, ip TEXT,
            attempts INTEGER DEFAULT 0, used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_login_codes_email ON login_codes(email);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            created_at TEXT, expires_at TEXT, last_seen TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AuthError(400, "Enter a valid email address")
    return email


# --- email -----------------------------------------------------------------

def send_code_email(email: str, code: str):
    if os.environ.get("AUTH_DEV_LOG_CODES") == "1":
        print(f"[auth] DEV login code for {email}: {code}", flush=True)
        return
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        raise AuthError(503, "Email sign-in is not configured yet")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = f"{code} is your TurnaroundIQ sign-in code"
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(
        f"Your TurnaroundIQ sign-in code is {code}\n\n"
        f"It expires in {CODE_TTL_MIN} minutes. If you didn't ask for it, ignore this email."
    )
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
            if user:
                s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ctx)
            if user:
                s.login(user, password)
            s.send_message(msg)


# --- flow ------------------------------------------------------------------

def purge_expired(conn):
    """Housekeeping promised in the privacy policy: codes kept 24h, dead sessions dropped."""
    day_ago = (_now() - timedelta(days=1)).isoformat()
    conn.execute("DELETE FROM login_codes WHERE created_at < ?", (day_ago,))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))


def delete_account(user_id: str):
    """Erase a web account and everything stored against it."""
    ensure_auth_tables()
    conn = get_db()
    email = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    for sql in (
        "DELETE FROM sessions WHERE user_id = ?",
        "DELETE FROM tracked_bets WHERE app_user_id = ?",
        "DELETE FROM paper_settings WHERE app_user_id = ?",
        "DELETE FROM user_prefs WHERE app_user_id = ?",
        "DELETE FROM subscribers WHERE app_user_id = ?",
        "DELETE FROM users WHERE id = ?",
    ):
        try:
            conn.execute(sql, (user_id,))
        except Exception:
            pass  # table not created yet
    if email:
        conn.execute("DELETE FROM login_codes WHERE email = ?", (email[0],))
    conn.commit()
    conn.close()


def start(email: str, ip: str = ""):
    email = normalize_email(email)
    _secret()
    ensure_auth_tables()
    conn = get_db()
    purge_expired(conn)
    hour_ago = (_now() - timedelta(hours=1)).isoformat()
    by_email = conn.execute(
        "SELECT COUNT(*) FROM login_codes WHERE email = ? AND created_at > ?", (email, hour_ago)
    ).fetchone()[0]
    by_ip = conn.execute(
        "SELECT COUNT(*) FROM login_codes WHERE ip = ? AND created_at > ?", (ip, hour_ago)
    ).fetchone()[0] if ip else 0
    if by_email >= CODES_PER_EMAIL_PER_HOUR or by_ip >= CODES_PER_IP_PER_HOUR:
        conn.close()
        raise AuthError(429, "Too many codes requested — try again in an hour")
    code = f"{secrets.randbelow(10**6):06d}"
    conn.execute(
        "INSERT INTO login_codes (email, code_hash, ip, created_at, expires_at) VALUES (?,?,?,?,?)",
        (email, _h(email + ":" + code), ip, _now().isoformat(),
         (_now() + timedelta(minutes=CODE_TTL_MIN)).isoformat()),
    )
    conn.commit()
    conn.close()
    send_code_email(email, code)


def verify(email: str, code: str):
    email = normalize_email(email)
    code = re.sub(r"\D", "", code or "")
    ensure_auth_tables()
    conn = get_db()
    row = conn.execute(
        """SELECT id, code_hash, attempts, expires_at FROM login_codes
           WHERE email = ? AND used = 0 ORDER BY id DESC LIMIT 1""",
        (email,),
    ).fetchone()
    if not row or row[3] < _now().isoformat() or row[2] >= CODE_MAX_ATTEMPTS:
        conn.close()
        raise AuthError(400, "That code has expired — request a new one")
    if not hmac.compare_digest(row[1], _h(email + ":" + code)):
        conn.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?", (row[0],))
        conn.commit()
        conn.close()
        raise AuthError(400, "Wrong code")
    conn.execute("UPDATE login_codes SET used = 1 WHERE id = ?", (row[0],))

    user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if user:
        user_id = user[0]
    else:
        user_id = "u_" + secrets.token_hex(12)
        conn.execute("INSERT INTO users (id, email, created_at) VALUES (?,?,?)",
                     (user_id, email, _now().isoformat()))
    token = "s_" + secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen) VALUES (?,?,?,?,?)",
        (_h(token), user_id, _now().isoformat(),
         (_now() + timedelta(days=SESSION_DAYS)).isoformat(), _now().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"token": token, "user_id": user_id, "email": email}


def resolve_session(token: str):
    """Session token -> user id, or None."""
    ensure_auth_tables()
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (_h(token),)
    ).fetchone()
    if row and row[1] >= _now().isoformat():
        conn.execute("UPDATE sessions SET last_seen = ? WHERE token_hash = ?",
                     (_now().isoformat(), _h(token)))
        conn.commit()
        conn.close()
        return row[0]
    conn.close()
    return None


def logout(token: str):
    ensure_auth_tables()
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_h(token),))
    conn.commit()
    conn.close()


def email_for(user_id: str):
    ensure_auth_tables()
    conn = get_db()
    row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else None
