"""
Extra-place offers from a pasted daily list, e.g.

    14:10 Killarney
    (4 places, 1/5 odds)
    bet365
    Betway (12+)
    (5 places, 1/5 odds)
    Sky Bet (12+)

"(12+)" = the offer only stands with at least 12 runners. parse() reads the
text; match() finds the stored races (same date, time and course).
"""

from __future__ import annotations

import re
from typing import Optional

RACE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s+(.+?)\s*$")
TERMS = re.compile(r"^\s*\(\s*(\d+)\s*places?\s*,\s*(\d+\s*/\s*\d+)\s*(?:odds)?\s*\)\s*$", re.I)
BOOK = re.compile(r"^\s*(.+?)\s*(?:\(\s*(\d+)\s*\+\s*(?:runners)?\s*\))?\s*$", re.I)


def parse(text: str) -> tuple[list[dict], list[str]]:
    """-> ([{time, course, places, fraction, bookmaker, min_runners}], lines that were not understood)."""
    offers, skipped = [], []
    race = terms = None
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = RACE.match(line)
        if m:
            race, terms = (f"{int(m.group(1)):02d}:{m.group(2)}", m.group(3)), None
            continue
        m = TERMS.match(line)
        if m:
            terms = (int(m.group(1)), m.group(2).replace(" ", ""))
            continue
        m = BOOK.match(line)
        if race and terms and m and len(m.group(1)) <= 40:
            offers.append({"time": race[0], "course": race[1], "places": terms[0], "fraction": terms[1],
                           "bookmaker": m.group(1), "min_runners": int(m.group(2)) if m.group(2) else None})
        else:
            skipped.append(line.strip())
    return offers, skipped


def course_key(name: Optional[str]) -> str:
    s = re.sub(r"\(.*?\)", " ", str(name or "").lower())
    s = re.sub(r"\b(great|park|racecourse|aw|the)\b", " ", s)
    return re.sub(r"[^a-z]", "", s)


def match(offers: list[dict], races: list[dict]) -> tuple[list[tuple[int, dict]], list[str]]:
    """Pair offers with races ({race_id, time, course}). Returns ([(race_id, offer)], unmatched 'time course')."""
    by_time: dict = {}
    for r in races:
        by_time.setdefault(r.get("time"), []).append(r)
    out, missing = [], []
    for o in offers:
        k = course_key(o["course"])
        hit = [r for r in by_time.get(o["time"], [])
               if k and (course_key(r.get("course")).startswith(k) or k.startswith(course_key(r.get("course")) or "?"))]
        if hit:
            out.append((hit[0]["race_id"], o))
        else:
            label = f"{o['time']} {o['course']}"
            if label not in missing:
                missing.append(label)
    return out, missing


def apply(text: str, date: str) -> dict:
    """Parse a pasted list and save the offers on that day's stored races (shared with every user)."""
    from racing import store
    from racing.extra_place import parse_fraction

    offers, skipped = parse(text)
    races = [{"race_id": r["race_id"], "time": r.get("time"), "course": r.get("course")}
             for r in store.races_on(date)]
    pairs, missing = match(offers, races)
    saved, race_ids = 0, set()
    for rid, o in pairs:
        frac = parse_fraction(o["fraction"])
        if not frac or frac > 1:
            skipped.append(f"{o['time']} {o['course']}: fraction {o['fraction']}")
            continue
        saved += store.set_offers([rid], o["bookmaker"], o["places"], frac, min_runners=o["min_runners"])
        race_ids.add(rid)
    return {"offers": saved, "races": len(race_ids), "not_found": missing, "not_understood": skipped[:20]}
