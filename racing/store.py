"""
SQLite storage for The Stables (tables prefixed rac_ so they never clash with
the football tables in two_up.db).

Racecards come in as JSON (see scripts/stables_import.py for the format), are
normalised into courses / races / horses / jockeys / trainers / runners /
markets / exchange_markets / results, and read back as the race dicts that
racing/engine.py prices.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from database import get_db
from racing.extra_place import parse_fraction

SCHEMA = """
CREATE TABLE IF NOT EXISTS rac_courses (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, country TEXT, surface TEXT,
  direction TEXT, track_type TEXT);
CREATE TABLE IF NOT EXISTS rac_races (
  id INTEGER PRIMARY KEY, external_id TEXT UNIQUE, date TEXT NOT NULL, time TEXT,
  course_id INTEGER REFERENCES rac_courses(id), name TEXT, distance TEXT, class TEXT,
  going TEXT, field_size INTEGER, handicap INTEGER DEFAULT 0, race_type TEXT, surface TEXT);
CREATE TABLE IF NOT EXISTS rac_horses (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, age INTEGER, sex TEXT, sire TEXT, dam TEXT);
CREATE TABLE IF NOT EXISTS rac_jockeys (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS rac_trainers (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS rac_runners (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL REFERENCES rac_races(id),
  horse_id INTEGER NOT NULL REFERENCES rac_horses(id), jockey_id INTEGER, trainer_id INTEGER,
  number INTEGER, draw INTEGER, weight TEXT, official_rating INTEGER, form TEXT,
  non_runner INTEGER DEFAULT 0, UNIQUE(race_id, horse_id));
CREATE TABLE IF NOT EXISTS rac_results (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, horse_id INTEGER NOT NULL,
  finish_position INTEGER, finish_time TEXT, beaten_lengths REAL, starting_price REAL,
  exchange_sp REAL, UNIQUE(race_id, horse_id));
CREATE TABLE IF NOT EXISTS rac_features (
  id INTEGER PRIMARY KEY, horse_id INTEGER NOT NULL, race_id INTEGER NOT NULL,
  speed_rating REAL, form_rating REAL, distance_rating REAL, going_rating REAL,
  course_rating REAL, recent_form REAL, days_since_run INTEGER, UNIQUE(race_id, horse_id));
CREATE TABLE IF NOT EXISTS rac_markets (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, horse_id INTEGER NOT NULL,
  bookmaker TEXT NOT NULL, win_odds REAL, place_odds REAL, places_paid INTEGER,
  place_fraction REAL, timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rac_exchange_markets (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, horse_id INTEGER NOT NULL,
  back_price REAL, lay_price REAL, volume REAL, liquidity REAL, timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rac_position_probabilities (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, horse_id INTEGER NOT NULL,
  p1 REAL, p2 REAL, p3 REAL, p4 REAL, p5 REAL, p6 REAL, p7 REAL, p8 REAL, p9 REAL,
  generated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rac_model_predictions (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, horse_id INTEGER NOT NULL,
  win_probability REAL, top3_probability REAL, top4_probability REAL,
  top5_probability REAL, top6_probability REAL, edge REAL, confidence INTEGER,
  expected_value REAL, generated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rac_opportunities (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, horse_id INTEGER NOT NULL,
  bookmaker TEXT, places_paid INTEGER, model_probability REAL, market_probability REAL,
  edge REAL, expected_value REAL, confidence INTEGER, stake_recommendation REAL,
  grade TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rac_offers (
  id INTEGER PRIMARY KEY, race_id INTEGER NOT NULL, bookmaker TEXT NOT NULL,
  places INTEGER NOT NULL, fraction REAL, timestamp TEXT NOT NULL,
  UNIQUE(race_id, bookmaker));
CREATE TABLE IF NOT EXISTS rac_calibration (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS rac_races_date ON rac_races(date);
CREATE INDEX IF NOT EXISTS rac_markets_race ON rac_markets(race_id, horse_id, timestamp);
CREATE INDEX IF NOT EXISTS rac_exchange_race ON rac_exchange_markets(race_id, horse_id, timestamp);
"""

FEATURE_COLS = ("speed_rating", "form_rating", "distance_rating", "going_rating",
                "course_rating", "recent_form", "days_since_run")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_tables(conn=None):
    own = conn is None
    conn = conn or get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    if own:
        conn.close()


def _named(conn, table: str, name: str, **extra) -> Optional[int]:
    name = (name or "").strip()
    if not name:
        return None
    row = conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    if row:
        if extra:
            sets = {k: v for k, v in extra.items() if v not in (None, "")}
            if sets:
                conn.execute(f"UPDATE {table} SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?",
                             (*sets.values(), row[0]))
        return row[0]
    cols = ["name", *extra.keys()]
    cur = conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                       (name, *extra.values()))
    return cur.lastrowid


def import_card(card: dict, conn=None) -> dict:
    """Upsert a {"races": [...]} card. Re-importing adds a new market snapshot."""
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    ts = card.get("timestamp") or _now()
    n_races = n_runners = n_results = 0
    for r in card.get("races") or []:
        course_id = _named(conn, "rac_courses", r.get("course") or "Unknown",
                           country=r.get("country"), surface=r.get("surface"),
                           direction=r.get("direction"), track_type=r.get("track_type"))
        ext = r.get("id") or f"{r.get('date')}|{r.get('time')}|{r.get('course')}"
        runners = r.get("runners") or []
        vals = dict(date=r.get("date"), time=r.get("time"), course_id=course_id, name=r.get("name"),
                    distance=r.get("distance"), class_=r.get("race_class"), going=r.get("going"),
                    field_size=sum(1 for x in runners if not x.get("non_runner")),
                    handicap=int(bool(r.get("handicap"))), race_type=r.get("race_type"),
                    surface=r.get("surface"))
        row = conn.execute("SELECT id FROM rac_races WHERE external_id = ?", (ext,)).fetchone()
        cols = [k.rstrip("_") for k in vals]
        if row:
            race_id = row[0]
            conn.execute(f"UPDATE rac_races SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                         (*vals.values(), race_id))
        else:
            race_id = conn.execute(
                f"INSERT INTO rac_races (external_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})",
                (ext, *vals.values())).lastrowid
        n_races += 1
        for t in r.get("terms") or []:
            conn.execute(
                "INSERT INTO rac_offers (race_id, bookmaker, places, fraction, timestamp) VALUES (?,?,?,?,?) "
                "ON CONFLICT(race_id, bookmaker) DO UPDATE SET places=excluded.places, "
                "fraction=excluded.fraction, timestamp=excluded.timestamp",
                (race_id, t.get("bookmaker"), int(t.get("places")), parse_fraction(t.get("fraction")), ts))
        for x in runners:
            horse_id = _named(conn, "rac_horses", x.get("horse") or x.get("name"), age=x.get("age"),
                              sex=x.get("sex"), sire=x.get("sire"), dam=x.get("dam"))
            if horse_id is None:
                continue
            jockey_id = _named(conn, "rac_jockeys", x.get("jockey"))
            trainer_id = _named(conn, "rac_trainers", x.get("trainer"))
            conn.execute(
                "INSERT INTO rac_runners (race_id, horse_id, jockey_id, trainer_id, number, draw, weight, "
                "official_rating, form, non_runner) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(race_id, horse_id) DO UPDATE SET jockey_id=excluded.jockey_id, "
                "trainer_id=excluded.trainer_id, number=excluded.number, draw=excluded.draw, "
                "weight=excluded.weight, official_rating=excluded.official_rating, form=excluded.form, "
                "non_runner=excluded.non_runner",
                (race_id, horse_id, jockey_id, trainer_id, x.get("number"), x.get("draw"),
                 x.get("weight"), x.get("official_rating"), x.get("form"), int(bool(x.get("non_runner")))))
            n_runners += 1
            for book, odds in (x.get("odds") or {}).items():
                conn.execute("INSERT INTO rac_markets (race_id, horse_id, bookmaker, win_odds, timestamp) "
                             "VALUES (?,?,?,?,?)", (race_id, horse_id, book, odds, ts))
            ex = x.get("exchange") or {}
            if ex.get("back") or ex.get("lay"):
                conn.execute("INSERT INTO rac_exchange_markets (race_id, horse_id, back_price, lay_price, "
                             "volume, liquidity, timestamp) VALUES (?,?,?,?,?,?,?)",
                             (race_id, horse_id, ex.get("back"), ex.get("lay"), ex.get("volume"),
                              ex.get("liquidity"), ts))
            feats = x.get("features") or {}
            if any(feats.get(k) is not None for k in FEATURE_COLS):
                conn.execute(
                    f"INSERT OR REPLACE INTO rac_features (race_id, horse_id, {', '.join(FEATURE_COLS)}) "
                    f"VALUES (?,?,{', '.join('?' * len(FEATURE_COLS))})",
                    (race_id, horse_id, *(feats.get(k) for k in FEATURE_COLS)))
        for pos, entry in enumerate(r.get("result") or [], start=1):
            e = entry if isinstance(entry, dict) else {"horse": entry, "position": pos}
            horse_id = _named(conn, "rac_horses", e.get("horse"))
            if horse_id is None:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO rac_results (race_id, horse_id, finish_position, finish_time, "
                "beaten_lengths, starting_price, exchange_sp) VALUES (?,?,?,?,?,?,?)",
                (race_id, horse_id, e.get("position") or pos, e.get("finish_time"),
                 e.get("beaten_lengths"), e.get("starting_price"), e.get("exchange_sp")))
            n_results += 1
    conn.commit()
    if own:
        conn.close()
    return {"races": n_races, "runners": n_runners, "results": n_results}


def _latest(conn, sql, params):
    """{horse_id: row} keeping the newest timestamp per horse (rows ordered by timestamp)."""
    out = {}
    for row in conn.execute(sql, params):
        out[row[0]] = row
    return out


def load_race(conn, race_id: int) -> Optional[dict]:
    r = conn.execute(
        "SELECT r.id, r.date, r.time, c.name, r.name, r.distance, r.class, r.going, r.handicap, "
        "r.race_type, r.surface FROM rac_races r LEFT JOIN rac_courses c ON c.id = r.course_id "
        "WHERE r.id = ?", (race_id,)).fetchone()
    if not r:
        return None
    race = dict(zip(("race_id", "date", "time", "course", "name", "distance", "race_class",
                     "going", "handicap", "race_type", "surface"), r))
    race["handicap"] = bool(race["handicap"])
    odds = {}
    for hid, book, price in conn.execute(
            "SELECT horse_id, bookmaker, win_odds FROM rac_markets WHERE race_id = ? ORDER BY timestamp",
            (race_id,)):
        odds.setdefault(hid, {})[book] = price
    ex = _latest(conn, "SELECT horse_id, back_price, lay_price, volume FROM rac_exchange_markets "
                       "WHERE race_id = ? ORDER BY timestamp", (race_id,))
    feats = {row[0]: dict(zip(FEATURE_COLS, row[1:])) for row in conn.execute(
        f"SELECT horse_id, {', '.join(FEATURE_COLS)} FROM rac_features WHERE race_id = ?", (race_id,))}
    race["runners"] = []
    for (hid, name, num, draw, weight, rating, form, nr, jockey, trainer, age) in conn.execute(
            "SELECT h.id, h.name, x.number, x.draw, x.weight, x.official_rating, x.form, x.non_runner, "
            "j.name, t.name, h.age FROM rac_runners x JOIN rac_horses h ON h.id = x.horse_id "
            "LEFT JOIN rac_jockeys j ON j.id = x.jockey_id LEFT JOIN rac_trainers t ON t.id = x.trainer_id "
            "WHERE x.race_id = ? ORDER BY x.number, h.name", (race_id,)):
        e = ex.get(hid)
        race["runners"].append({
            "horse_id": hid, "name": name, "number": num, "draw": draw, "weight": weight,
            "official_rating": rating, "form": form, "non_runner": bool(nr), "jockey": jockey,
            "trainer": trainer, "age": age, "odds": odds.get(hid, {}),
            "exchange": {"back": e[1], "lay": e[2], "volume": e[3]} if e else None,
            "features": feats.get(hid),
        })
    race["terms"] = [{"bookmaker": b, "places": p, "fraction": f} for b, p, f in conn.execute(
        "SELECT bookmaker, places, fraction FROM rac_offers WHERE race_id = ? ORDER BY bookmaker", (race_id,))]
    return race


def races_on(date: str, conn=None) -> list[dict]:
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    ids = [x[0] for x in conn.execute("SELECT id FROM rac_races WHERE date = ? ORDER BY time, id", (date,))]
    out = [load_race(conn, i) for i in ids]
    if own:
        conn.close()
    return out


def race_dates(conn=None, limit: int = 14) -> list[str]:
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    out = [x[0] for x in conn.execute(
        "SELECT DISTINCT date FROM rac_races ORDER BY date DESC LIMIT ?", (limit,))]
    if own:
        conn.close()
    return out


def races_with_results(conn=None) -> list[dict]:
    """Past races with a finishing order, priced from SP (else latest market), for calibration."""
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    out = []
    ids = [x[0] for x in conn.execute("SELECT DISTINCT race_id FROM rac_results")]
    for rid in ids:
        res = conn.execute("SELECT horse_id, finish_position, starting_price, exchange_sp FROM rac_results "
                           "WHERE race_id = ? ORDER BY finish_position", (rid,)).fetchall()
        race = load_race(conn, rid)
        if not race:
            continue
        runners = [x for x in race["runners"] if not x["non_runner"]]
        sp = {h: (bsp or isp) for h, _, isp, bsp in res}
        for x in runners:
            if sp.get(x["horse_id"]):
                x["win_odds"] = sp[x["horse_id"]]
                x["exchange"] = None
        idx = {x["horse_id"]: i for i, x in enumerate(runners)}
        order = [idx[h] for h, pos, _, _ in res if h in idx and pos]
        out.append({"race": {**race, "runners": runners}, "order": order})
    if own:
        conn.close()
    return out


def set_offers(race_ids: list[int], bookmaker: str, places: int, fraction: float, conn=None) -> int:
    """Add / replace one bookmaker's extra-place terms on several races. Returns races updated."""
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    ts = _now()
    n = 0
    for rid in race_ids:
        if not conn.execute("SELECT 1 FROM rac_races WHERE id = ?", (rid,)).fetchone():
            continue
        conn.execute(
            "INSERT INTO rac_offers (race_id, bookmaker, places, fraction, timestamp) VALUES (?,?,?,?,?) "
            "ON CONFLICT(race_id, bookmaker) DO UPDATE SET places=excluded.places, "
            "fraction=excluded.fraction, timestamp=excluded.timestamp",
            (rid, bookmaker, int(places), float(fraction), ts))
        n += 1
    conn.commit()
    if own:
        conn.close()
    return n


def delete_offer(race_id: int, bookmaker: str, conn=None) -> int:
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    n = conn.execute("DELETE FROM rac_offers WHERE race_id = ? AND bookmaker = ?", (race_id, bookmaker)).rowcount
    conn.commit()
    if own:
        conn.close()
    return n


def last_snapshot(conn=None) -> Optional[str]:
    """Time of the newest exchange price snapshot (any source), ISO."""
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    row = conn.execute("SELECT MAX(timestamp) FROM rac_exchange_markets").fetchone()
    if own:
        conn.close()
    return row[0] if row else None


def prune_snapshots(keep_days: float = 1.0, conn=None) -> int:
    """
    Every collector run adds a price snapshot per runner. Older than keep_days,
    keep only the last snapshot per runner (the closing price, useful later).
    """
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
    n = 0
    for table in ("rac_exchange_markets", "rac_markets"):
        key = "race_id, horse_id" if table == "rac_exchange_markets" else "race_id, horse_id, bookmaker"
        n += conn.execute(
            f"DELETE FROM {table} WHERE timestamp < ? AND id NOT IN "
            f"(SELECT MAX(id) FROM {table} GROUP BY {key})", (cutoff,)).rowcount
    conn.commit()
    if own:
        conn.close()
    return n


def save_calibration(payload: dict, conn=None):
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    conn.execute("INSERT INTO rac_calibration (created_at, payload) VALUES (?, ?)", (_now(), json.dumps(payload)))
    conn.commit()
    if own:
        conn.close()


def latest_calibration(conn=None) -> dict:
    own = conn is None
    conn = conn or get_db()
    ensure_tables(conn)
    row = conn.execute("SELECT created_at, payload FROM rac_calibration ORDER BY id DESC LIMIT 1").fetchone()
    if own:
        conn.close()
    if not row:
        return {}
    return {**json.loads(row[1]), "created_at": row[0]}


def save_priced(priced: dict, conn=None):
    """Persist one priced race into position_probabilities / model_predictions / opportunities."""
    rid = priced.get("race_id")
    if not rid:
        return
    own = conn is None
    conn = conn or get_db()
    ts = _now()
    ids = {name: hid for hid, name in conn.execute(
        "SELECT h.id, h.name FROM rac_runners x JOIN rac_horses h ON h.id = x.horse_id WHERE x.race_id = ?", (rid,))}
    for row in priced["runners"]:
        hid = ids.get(row["name"])
        if hid is None:
            continue
        pos = (row["positions"] + [0.0] * 9)[:9]
        conn.execute("INSERT INTO rac_position_probabilities (race_id, horse_id, p1, p2, p3, p4, p5, p6, p7, p8, "
                     "p9, generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (rid, hid, *pos, ts))
        best = max(row["offers"], key=lambda o: o["each_way_ev"], default=None)
        conn.execute(
            "INSERT INTO rac_model_predictions (race_id, horse_id, win_probability, top3_probability, "
            "top4_probability, top5_probability, top6_probability, edge, confidence, expected_value, "
            "generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rid, hid, row["win_probability"], row["top3_probability"], row["top4_probability"],
             row["top5_probability"], row["top6_probability"], best and best["edge"],
             best and best["confidence"], best and best["each_way_ev"], ts))
    for o in priced["opportunities"]:
        hid = ids.get(o["horse"])
        if hid is None:
            continue
        conn.execute(
            "INSERT INTO rac_opportunities (race_id, horse_id, bookmaker, places_paid, model_probability, "
            "market_probability, edge, expected_value, confidence, stake_recommendation, grade, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, hid, o["bookmaker"], o["places_paid"], o["model_probability"], o["market_probability"],
             o["edge"], o["each_way_ev"], o["confidence"], o["recommended_stake_pct"], o["grade"], ts))
    conn.commit()
    if own:
        conn.close()
