"""FTD waitlist API.

POST /api/waitlist  {email, source?, product?, colour?, size?, website?}
  -> 200 {"ok": true, "already": bool}   stored (and synced to Resend if configured)
  -> 4xx/5xx {"ok": false, "error": "..."}

Signups are always written to SQLite first, so nothing is lost if the email
provider is down. When RESEND_API_KEY and RESEND_AUDIENCE_ID are set, each new
address is also added to that Resend audience; a failed sync is logged and
retried by `python3 server/waitlist_api.py sync`.

Run: uvicorn server.waitlist_api:app --host 127.0.0.1 --port 8090
"""

import logging
import os
import re
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

HERE = Path(__file__).resolve().parent


def _load_env_file(path):
    """Minimal KEY=VALUE loader for server/.env in development (never overrides real env)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(HERE / ".env")

DB_PATH = Path(os.environ.get("FTD_WAITLIST_DB", HERE / "ftd_waitlist.db"))
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_AUDIENCE_ID = os.environ.get("RESEND_AUDIENCE_ID", "").strip()
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get("FTD_ALLOWED_ORIGINS", "").split(",") if o.strip()}

SOURCES = {"landing", "product"}
SIZES = {"XS", "S", "M", "L", "XL", "XXL"}
COLOURS = {"black", "grey"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
SLUG_RE = re.compile(r"^[a-z0-9-]{1,64}$")

log = logging.getLogger("ftd.waitlist")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="FTD waitlist", docs_url=None, redoc_url=None, openapi_url=None)
_db_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(db()) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                source TEXT NOT NULL,
                product TEXT,
                colour TEXT,
                size TEXT,
                created_at TEXT NOT NULL,
                synced_at TEXT
            )"""
        )
        # one row per product colourway someone asked to be told about, with their size
        conn.execute(
            """CREATE TABLE IF NOT EXISTS waitlist_interest (
                email TEXT NOT NULL COLLATE NOCASE,
                product TEXT NOT NULL,
                colour TEXT NOT NULL DEFAULT '',
                size TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (email, product, colour)
            )"""
        )
        # databases created before colourways existed
        if "colour" not in {r["name"] for r in conn.execute("PRAGMA table_info(waitlist)")}:
            conn.execute("ALTER TABLE waitlist ADD COLUMN colour TEXT")


init_db()


# ------------------------------------------------------------------ rate limit

_hits = defaultdict(deque)
RATE_WINDOW, RATE_MAX = 600, 8  # 8 attempts per IP per 10 minutes


def rate_limited(ip):
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_MAX:
        return True
    q.append(now)
    return False


def client_ip(request: Request):
    # Caddy sets X-Forwarded-For; the API only listens on 127.0.0.1 behind it
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def fail(status, message):
    return JSONResponse({"ok": False, "error": message}, status_code=status)


# ------------------------------------------------------------------ resend sync

def resend_enabled():
    return bool(RESEND_API_KEY and RESEND_AUDIENCE_ID)


def push_to_resend(email):
    """Add a contact to the Resend audience. Returns True when Resend accepted it."""
    try:
        r = requests.post(
            f"https://api.resend.com/audiences/{RESEND_AUDIENCE_ID}/contacts",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"email": email, "unsubscribed": False},
            timeout=8,
        )
    except requests.RequestException as e:
        log.warning("resend sync failed for a signup: %s", e.__class__.__name__)
        return False
    if r.status_code in (200, 201):
        return True
    # an address already in the audience is fine
    if r.status_code in (409, 422) and "already" in r.text.lower():
        return True
    log.warning("resend sync rejected (HTTP %s): %s", r.status_code, r.text[:200])
    return False


def sync_one(email):
    if push_to_resend(email):
        with _db_lock, closing(db()) as conn, conn:
            conn.execute("UPDATE waitlist SET synced_at=? WHERE email=?", (now_iso(), email))


def sync_pending():
    with closing(db()) as conn:
        rows = [r["email"] for r in conn.execute("SELECT email FROM waitlist WHERE synced_at IS NULL")]
    done = 0
    for email in rows:
        if push_to_resend(email):
            with closing(db()) as conn, conn:
                conn.execute("UPDATE waitlist SET synced_at=? WHERE email=?", (now_iso(), email))
            done += 1
        time.sleep(0.6)  # stay well under Resend's rate limit
    return done, len(rows)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ routes

@app.get("/api/health")
def health():
    return {"ok": True, "resend": resend_enabled()}


@app.post("/api/waitlist")
async def join(request: Request):
    origin = request.headers.get("origin")
    if ALLOWED_ORIGINS and origin and origin not in ALLOWED_ORIGINS:
        return fail(403, "Signups from this site aren't accepted.")
    if rate_limited(client_ip(request)):
        return fail(429, "Too many attempts. Wait a few minutes and try again.")
    try:
        data = await request.json()
    except Exception:
        return fail(400, "Bad request.")
    if not isinstance(data, dict):
        return fail(400, "Bad request.")

    # honeypot: pretend success so bots learn nothing, store nothing
    if str(data.get("website") or "").strip():
        return {"ok": True, "already": False}

    email = str(data.get("email") or "").strip()
    if len(email) > 254 or not EMAIL_RE.match(email):
        return fail(422, "That email address doesn't look right.")
    source = data.get("source") if data.get("source") in SOURCES else "landing"
    product = data.get("product")
    product = product if isinstance(product, str) and SLUG_RE.match(product) else None
    size = data.get("size") if data.get("size") in SIZES else None
    colour = data.get("colour") if data.get("colour") in COLOURS else None

    try:
        with _db_lock, closing(db()) as conn, conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO waitlist (email, source, product, colour, size, created_at) VALUES (?,?,?,?,?,?)",
                (email, source, product, colour, size, now_iso()),
            )
            already = cur.rowcount == 0
            if product:
                conn.execute(
                    "INSERT INTO waitlist_interest (email, product, colour, size, created_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(email, product, colour) DO UPDATE SET size=excluded.size",
                    (email, product, colour or "", size, now_iso()),
                )
    except sqlite3.Error:
        log.exception("waitlist write failed")
        return fail(500, "We couldn't save your email just now. Try again shortly.")

    if not already and resend_enabled():
        threading.Thread(target=sync_one, args=(email,), daemon=True).start()
    return {"ok": True, "already": already}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sync":
        if not resend_enabled():
            sys.exit("RESEND_API_KEY and RESEND_AUDIENCE_ID are not set")
        done, total = sync_pending()
        print(f"synced {done}/{total}")
    elif cmd == "count":
        with closing(db()) as conn:
            print(conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0])
    elif cmd == "export":
        with closing(db()) as conn:
            print("email,source,product,colour,size,created_at")
            for r in conn.execute("SELECT email, source, product, colour, size, created_at FROM waitlist ORDER BY id"):
                print(",".join(str(v or "") for v in r))
    elif cmd == "interest":
        with closing(db()) as conn:
            print("product,colour,size,count")
            for r in conn.execute("SELECT product, colour, size, COUNT(*) FROM waitlist_interest "
                                  "GROUP BY product, colour, size ORDER BY product, colour, size"):
                print(",".join(str(v or "") for v in r))
    else:
        print("usage: python3 server/waitlist_api.py sync|count|export|interest")
