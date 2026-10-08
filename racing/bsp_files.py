"""
Betfair's free daily BSP files (promo.betfair.com): every UK and Irish race,
win market and "To Be Placed" market, with each runner's BSP and win/lose flag.

fetch()         cached download (data/bsp/) with curl, through BETFAIR_PROXY when set:
                Betfair refuses non-UK servers, so the VPS uses the SSH link
                to the UK server, as the collector does.
history_rows()  one day's files -> rac_history rows (horse, course, trip,
                race type, won / placed, and the chances the BSPs gave), so
                live runners get recent course / distance / "vs prices" records.
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "bsp"
HOSTS = ("https://promo.betfair.com",)   # www.betfairpromo.com now answers with a web page, not the files
PATH = "/betfairsp/prices/dwbfprices{region}{market}{d}.csv"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}   # what a plain curl test got 200 with
failures: list = []
_session = None


def proxy_setting() -> str:
    """The UK link (BETFAIR_PROXY), from the environment or /etc/turnaroundiq.env."""
    from collectors.betfair import setting

    return setting("BETFAIR_PROXY").strip()


def _http():
    global _session
    if _session is None:
        import requests

        _session = requests.Session()
        _session.headers.update(HEADERS)
        proxy = proxy_setting()
        if proxy:
            _session.proxies = {"https": proxy, "http": proxy}
    return _session


def _curl(url: str) -> tuple:
    """(status, text) with the curl binary. Betfair's file server let a plain curl through
    (HTTP 200) but refused Python's HTTP client (403) from the same server and link."""
    import shutil
    import subprocess

    if not shutil.which("curl"):
        return None, ""
    cmd = ["curl", "-s", "-L", "--max-time", "60", "-A", HEADERS["User-Agent"], "-w", "\n%{http_code}", url]
    proxy = proxy_setting()
    if proxy:
        cmd[1:1] = ["-x", proxy]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=90).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 0, f"{type(e).__name__}"
    body, _, code = out.rpartition("\n")
    return (int(code) if code.isdigit() else 0), body


def fetch(region: str, market: str, day: date, pause: float = 0.3) -> str:
    """Cached download; only real CSVs are cached, so a failed day is retried next run."""
    d = day.strftime("%d%m%Y")
    path = CACHE / f"{region}{market}{d}.csv"
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(errors="replace")
    for host in HOSTS:
        url = host + PATH.format(region=region, market=market, d=d)
        status, text = _curl(url)
        if status is None:            # no curl on this machine: Python's client
            try:
                r = _http().get(url, timeout=30)
                status, text = r.status_code, r.text
            except Exception as e:  # noqa: BLE001  network / proxy errors: try the next host
                failures.append(f"{url}: {type(e).__name__}: {e}"[:200])
                continue
        time.sleep(pause)
        if status == 200 and "EVENT_ID" in text[:300].upper():
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return text
        failures.append(f"{url}: HTTP {status}, starts {text[:80]!r}")
    return ""


def course_from_menu(menu: Optional[str]) -> str:
    """'UK / Kemp 5th Oct' / 'Kempton (IRE) 5th Oct' -> 'kemp' / 'kempton'."""
    s = str(menu or "").split(" / ")[-1]
    s = re.sub(r"\s+\d{1,2}(st|nd|rd|th)\s+\w+\s*$", "", s, flags=re.I)
    s = re.sub(r"\(.*?\)", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _date(event_dt: Optional[str]) -> Optional[str]:
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(event_dt).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def history_rows(win_text: str, place_text: str) -> list[dict]:
    """
    One day's win + place files -> rac_history rows. "Placed" means the first
    three (as in the Kaggle history): known exactly when the place market paid
    3; with 4+ paid an unplaced horse was not in the first three; with 2 paid a
    placed horse was. Otherwise left unknown, apart from winners.
    """
    from racing import market, nonfinish, positions
    from racing.backtest import _f, _rows
    from racing.live_features import distance_from_name, horse_key

    win = defaultdict(list)
    for r in _rows(win_text):
        win[(r.get("MENU_HINT"), r.get("EVENT_DT"))].append(r)
    place = defaultdict(dict)
    for r in _rows(place_text or ""):
        place[(r.get("MENU_HINT"), r.get("EVENT_DT"))][r.get("SELECTION_ID")] = r
    out = []
    for key, runners in win.items():
        day = _date(key[1])
        if not day or len(runners) < 2:
            continue
        bsp = [_f(r.get("BSP")) for r in runners]
        p = top3 = None
        if all(bsp):
            p = np.asarray(market.devig_multiplicative([float(b) for b in bsp]), float)  # BSP is close to fair
            top3 = positions.harville_top3(p)
        pl = place.get(key) or {}
        k = sum(1 for r in pl.values() if r.get("WIN_LOSE") == "1") if pl else 0
        name = runners[0].get("EVENT_NAME")
        for i, r in enumerate(runners):
            won = r.get("WIN_LOSE") == "1"
            in_place = (pl.get(r.get("SELECTION_ID")) or {}).get("WIN_LOSE")
            if won:
                placed = 1
            elif in_place is None or k == 0:
                placed = None
            elif k == 3:
                placed = 1 if in_place == "1" else 0
            elif k > 3:
                placed = 0 if in_place != "1" else None
            else:   # 2 places paid
                placed = 1 if in_place == "1" else None
            out.append({"race_ref": f"bsp:{runners[0].get('EVENT_ID')}", "date": day,
                        "course": course_from_menu(key[0]), "dist_f": distance_from_name(name), "going": None,
                        "race_type": nonfinish.race_type(name), "horse_key": horse_key(r.get("SELECTION_NAME")),
                        "jockey_key": None, "trainer_key": None, "pos": 1 if won else None, "placed": placed,
                        "source": "bsp",
                        "exp_win": float(p[i]) if p is not None else None,
                        "exp_place": float(top3[i]) if top3 is not None else None})
    return [r for r in out if r["horse_key"]]


def fill_bet_sp(days: int = 10, conn=None) -> int:
    """
    Betfair SP for tracked bets that have none yet (for the tracker's CLV), from the
    daily BSP files: the collector's own SP read after the off can come back empty.
    Matched on race date + horse name; only past days (the files land the next morning).
    """
    from database import get_db
    from racing import store
    from racing.live_features import horse_key

    own = conn is None
    conn = conn or get_db()
    store.ensure_tables(conn)
    today = date.today().isoformat()
    rows = conn.execute(
        "SELECT DISTINCT b.race_id, b.horse_id, b.horse, r.date FROM rac_bets b "
        "JOIN rac_races r ON r.id = b.race_id "
        "LEFT JOIN rac_results x ON x.race_id = b.race_id AND x.horse_id = b.horse_id "
        "WHERE x.exchange_sp IS NULL AND r.date < ? AND r.date >= date(?, ?)",
        (today, today, f"-{int(days)} day")).fetchall()
    by_day = defaultdict(list)
    for race_id, horse_id, horse, d in rows:
        by_day[str(d)[:10]].append((race_id, horse_id, horse_key(horse)))
    filled = 0
    for d, bets in by_day.items():
        sp = {}
        for region in ("uk", "ire"):
            for r in _rows_of(fetch(region, "win", date.fromisoformat(d))):
                v = _num(r.get("BSP"))
                if v and 1 < v < 10000:
                    sp[horse_key(r.get("SELECTION_NAME"))] = v
        for race_id, horse_id, key in bets:
            v = sp.get(key)
            if not v:
                continue
            cur = conn.execute("UPDATE rac_results SET exchange_sp = ? WHERE race_id = ? AND horse_id = ? "
                               "AND exchange_sp IS NULL", (v, race_id, horse_id))
            if not cur.rowcount:
                conn.execute("INSERT OR IGNORE INTO rac_results (race_id, horse_id, exchange_sp) VALUES (?,?,?)",
                             (race_id, horse_id, v))
            filled += 1
    conn.commit()
    if own:
        conn.close()
    return filled


def _rows_of(text: str) -> list:
    from racing.backtest import _rows

    return _rows(text) if text else []


def _num(v) -> Optional[float]:
    from racing.backtest import _f

    return _f(v)
