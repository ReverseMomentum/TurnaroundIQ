"""
Live runner features, built the same way as the training features
(racing/features.py), from Betfair's runner data (OR, draw, weight, form,
days since last run) and the rac_history table (Kaggle 2015+ plus our own
Betfair results as they arrive).

Names are matched on keys: horses without country suffix or punctuation,
people as first initial + surname ("Willie Mullins" and "W P Mullins" both
-> "w mullins").

Not available live: going (Betfair does not publish it, so going_rate stays
at the average) and speed ratings.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Optional

import numpy as np

from database import get_db
from racing import features as F
from racing import market, nonfinish, store


def horse_key(name: Optional[str]) -> str:
    s = re.sub(r"\([a-z]{2,4}\)", " ", str(name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def person_key(name: Optional[str]) -> Optional[str]:
    s = re.sub(r"\(.*?\)", " ", str(name or "").lower())
    parts = [p for p in re.sub(r"[^a-z' -]+", " ", s).replace("-", " ").split() if p]
    if not parts:
        return None
    return f"{parts[0][0]} {parts[-1]}" if len(parts) > 1 else parts[0]


def distance_from_name(name: Optional[str]) -> Optional[int]:
    """Betfair market names start with the trip: '2m4f Hcap Chs', '7f Mdn Stks', '1m Hcap'."""
    for m in re.finditer(r"\b(\d+)m(\d+)f\b|\b(\d+)m\b|\b(\d+)f\b", str(name or "").lower()):
        a, b, c, d = m.groups()
        if a:
            return int(a) * 8 + int(b)
        if c:
            return int(c) * 8
        return int(d)
    return None


def weight_lbs(v) -> Optional[float]:
    """'9-7' -> 133, '133' -> 133."""
    if v is None:
        return None
    s = str(v)
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)", s)
    if m:
        return int(m.group(1)) * 14 + int(m.group(2))
    try:
        x = float(s)
    except ValueError:
        return None
    return x if x > 50 else None


def _rate(rows, test=lambda r: True, m=F.SHRINK_HORSE):
    known = [r for r in rows if r["placed"] is not None and test(r)]
    return F.shrink(sum(r["placed"] for r in known), len(known), m)


def build(races: list[dict], conn=None, today: Optional[date] = None) -> dict:
    """{race_id: {horse_id: features}} for races from store.load_race."""
    own = conn is None
    conn = conn or get_db()
    store.ensure_tables(conn)
    today = today or date.today()
    runners = [(race, r) for race in races for r in race["runners"] if not r.get("non_runner")]
    hk = {horse_key(r["name"]) for _, r in runners}
    hist = {}
    for chunk in [list(hk)[i:i + 500] for i in range(0, len(hk), 500)]:
        q = ("SELECT horse_key, date, course, dist_f, jockey_key, placed FROM rac_history WHERE horse_key IN "
             f"({','.join('?' * len(chunk))})")
        for h, d, course, dist, jk, placed in conn.execute(q, chunk):
            hist.setdefault(h, []).append({"date": d, "course": (course or "").lower(), "dist_f": dist,
                                           "jockey": jk, "placed": placed})
    people = {}
    since = (today - timedelta(days=30)).isoformat()
    for col in ("jockey_key", "trainer_key"):
        people[col] = {k: (runs, placed) for k, runs, placed in conn.execute(
            f"SELECT {col}, COUNT(*), SUM(placed) FROM rac_history WHERE placed IS NOT NULL AND {col} IS NOT NULL "
            f"GROUP BY {col}")}
        people[col + "_30"] = {k: (runs, placed) for k, runs, placed in conn.execute(
            f"SELECT {col}, COUNT(*), SUM(placed) FROM rac_history WHERE placed IS NOT NULL AND {col} IS NOT NULL "
            f"AND date >= ? GROUP BY {col}", (since,))}
    if own:
        conn.close()

    out = {}
    for race in races:
        live = [r for r in race["runners"] if not r.get("non_runner")]
        if len(live) < 2:
            continue
        p, _, _ = market.fair_win_probs(live)
        rtype = nonfinish.race_type(race.get("race_type"), race.get("name"))
        dist = F.furlongs(race.get("distance")) or distance_from_name(race.get("name"))
        course = (race.get("course") or "").lower()
        rows = []
        for r, pi in zip(live, p):
            h = [x for x in hist.get(horse_key(r["name"]), []) if x["date"] < (race.get("date") or "9999")]
            jk, tk = person_key(r.get("jockey")), person_key(r.get("trainer"))
            positions = F.parse_form(r.get("form"))
            days = r.get("days_since_run")
            if days is None and h:
                try:
                    days = (date.fromisoformat(race["date"]) - date.fromisoformat(max(x["date"] for x in h)[:10])).days
                except (ValueError, KeyError, TypeError):
                    days = None
            f = {
                **F.form_features(positions),
                "first_run": 1.0 if not positions and not h and days is None else 0.0,
                "log_days": math.log1p(max(0, days)) if days is not None else 0.0,
                "course_rate": _rate(h, lambda x: x["course"] == course),
                "distance_rate": _rate(h, lambda x: dist is not None and x["dist_f"] is not None
                                       and abs(x["dist_f"] - dist) <= 1),
                "going_rate": None,
                "horse_jockey_rate": _rate(h, lambda x: jk is not None and x["jockey"] == jk),
                "jockey_rate": F.shrink(*_people(people["jockey_key"], jk), F.SHRINK_PEOPLE),
                "trainer_rate": F.shrink(*_people(people["trainer_key"], tk), F.SHRINK_PEOPLE),
                "jockey_30d": F.shrink(*_people(people["jockey_key_30"], jk), F.SHRINK_PEOPLE / 3),
                "trainer_30d": F.shrink(*_people(people["trainer_key_30"], tk), F.SHRINK_PEOPLE / 3),
                "or": r.get("official_rating"), "lbs": weight_lbs(r.get("weight")), "draw": r.get("draw"),
                "race_type": rtype, "history_runs": len(h),
            }
            rows.append(f)
        F.finish_race_features(rows, [1.0 / max(x, 1e-6) for x in p])
        out[race["race_id"]] = {r["horse_id"]: {k: F._clean(v) for k, v in f.items() if k not in ("race_type",)}
                                for r, f in zip(live, rows)}
    return out


def _people(table: dict, key) -> tuple:
    runs, placed = table.get(key, (0, 0)) if key else (0, 0)
    return (placed or 0), (runs or 0)


def refresh(race_ids: list[int]) -> int:
    """Build and store live features for these races."""
    conn = get_db()
    try:
        races = [store.load_race(conn, rid) for rid in race_ids]
        built = build([r for r in races if r], conn)
        for rid, by_horse in built.items():
            store.save_runner_features(rid, by_horse, conn)
        return sum(len(v) for v in built.values())
    finally:
        conn.close()


def history_from_results(race_ids: list[int]) -> int:
    """Add finished races (Betfair results) to rac_history. Placed = in the first three where known."""
    conn = get_db()
    rows = []
    try:
        for rid in race_ids:
            race = store.load_race(conn, rid)
            if not race:
                continue
            res = {hid: (pos, pw, ow) for hid, pos, pw, ow in conn.execute(
                "SELECT horse_id, finish_position, placed_within, outside_within FROM rac_results WHERE race_id = ?",
                (rid,))}
            for r in race["runners"]:
                if r.get("non_runner") or r["horse_id"] not in res:
                    continue
                pos, pw, ow = res[r["horse_id"]]
                placed = 1 if (pos == 1 or (pw is not None and pw <= 3)) else 0 if (ow is not None and ow >= 3) else None
                rows.append({"race_ref": f"live:{rid}", "date": race["date"], "course": race.get("course"),
                             "dist_f": distance_from_name(race.get("name")), "going": None,
                             "race_type": nonfinish.race_type(race.get("race_type"), race.get("name")),
                             "horse_key": horse_key(r["name"]), "jockey_key": person_key(r.get("jockey")),
                             "trainer_key": person_key(r.get("trainer")), "pos": 1 if pos == 1 else None,
                             "placed": placed, "source": "betfair"})
        return store.add_history(rows, conn)
    finally:
        conn.close()


def history_from_kaggle(paths, since_year: int = 2015) -> int:
    """Load Kaggle results from since_year into rac_history (run once)."""
    df = F._hwaitt_frame(paths, (since_year, 2100))
    if df.empty:
        return 0
    df = df[df["date"].dt.year >= since_year]
    rows = [{"race_ref": f"kaggle:{r.rid}", "date": r.date.strftime("%Y-%m-%d"), "course": r.course,
             "dist_f": None if r.dist_f is None or (isinstance(r.dist_f, float) and np.isnan(r.dist_f)) else int(r.dist_f),
             "going": r.going, "race_type": r.race_type, "horse_key": horse_key(r.horseName),
             "jockey_key": person_key(r.jockeyName), "trainer_key": person_key(r.trainerName),
             "pos": None if r.pos is None or (isinstance(r.pos, float) and np.isnan(r.pos)) else int(r.pos),
             "placed": int(r.placed), "source": "kaggle"} for r in df.itertuples()]
    n = 0
    for i in range(0, len(rows), 20000):
        n += store.add_history(rows[i:i + 20000])
    return n
