"""
Scorecard: what the app said before kick-off vs what happened.

The API's background loop logs the FTA% of every game in the next 24 hours
(the same numbers the Picks page shows; the last value before kick-off wins).
Once the results collector has the final score, `report()` lines them up:

    venv/bin/python -u scripts/scorecard.py               # last 30 days
    venv/bin/python -u scripts/scorecard.py --days 90

Actual FTA for a side = it went 2 goals up and did not win (match_results).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from database import get_db

DDL = """
CREATE TABLE IF NOT EXISTS prediction_log (
    match_id TEXT NOT NULL,
    team TEXT NOT NULL,
    opponent TEXT,
    league TEXT,
    is_home INTEGER,
    kickoff TEXT,
    fta_pct REAL,
    two_up_pct REAL,
    fail_pct REAL,
    model_version TEXT,
    logged_at TEXT,
    PRIMARY KEY (match_id, team)
)
"""
BANDS = [(0, 1), (1, 1.8), (1.8, 2.5), (2.5, 3), (3, 4), (4, 100)]
APP_FLOOR = 1.8   # the Picks page minimum


def ensure_table(conn=None):
    own = conn is None
    conn = conn or get_db()
    conn.execute(DDL)
    conn.commit()
    if own:
        conn.close()


def log_predictions(opportunities, now=None):
    """Upsert pre-kick-off predictions (opportunity dicts from rank_opportunities)."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for o in opportunities:
        if not o.get("match_id") or o.get("fta_pct") is None or not o.get("team"):
            continue
        try:
            ko = datetime.fromisoformat(str(o.get("kickoff")).replace("Z", "+00:00"))
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            if ko <= now:
                continue  # never overwrite once the game has started
        except ValueError:
            continue
        is_home = 1 if o["team"] == o.get("home_team") else 0
        opponent = o.get("away_team") if is_home else o.get("home_team")
        rows.append((str(o["match_id"]), o["team"], opponent, o.get("league") or "", is_home,
                     str(o.get("kickoff")), float(o["fta_pct"]), o.get("two_up_pct"),
                     o.get("turnaround_pct"), o.get("model_version"), now.isoformat()))
    if not rows:
        return 0
    conn = get_db()
    ensure_table(conn)
    conn.executemany(
        """INSERT INTO prediction_log (match_id, team, opponent, league, is_home, kickoff,
               fta_pct, two_up_pct, fail_pct, model_version, logged_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(match_id, team) DO UPDATE SET
               fta_pct=excluded.fta_pct, two_up_pct=excluded.two_up_pct,
               fail_pct=excluded.fail_pct, model_version=excluded.model_version,
               kickoff=excluded.kickoff, logged_at=excluded.logged_at""",
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def scored_rows(days=30, now=None):
    """[(fta_pct, actual 0/1, league)] for logged games with a final result."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    conn = get_db()
    ensure_table(conn)
    try:
        rows = conn.execute(
            """SELECT p.fta_pct, p.is_home, p.league, r.final_home, r.final_away, r.home_2up, r.away_2up
               FROM prediction_log p
               JOIN match_results r ON CAST(r.match_id AS TEXT) = p.match_id
               WHERE p.kickoff >= ?""",
            (since,),
        ).fetchall()
        pending = conn.execute(
            """SELECT COUNT(*) FROM prediction_log p
               WHERE p.kickoff >= ? AND p.kickoff < ?
                 AND NOT EXISTS (SELECT 1 FROM match_results r WHERE CAST(r.match_id AS TEXT) = p.match_id)""",
            (since, (now - timedelta(hours=3)).isoformat()),
        ).fetchone()[0]
    except Exception:
        rows, pending = [], 0
    finally:
        conn.close()
    out = []
    for fta, is_home, league, fh, fa, h2, a2 in rows:
        if fh is None or fa is None:
            continue
        up2, won = (h2, fh > fa) if is_home else (a2, fa > fh)
        out.append((float(fta), int(bool(up2) and not won), league or ""))
    return out, pending


def summarise(scored):
    n = len(scored)
    if not n:
        return None
    actual = sum(a for _, a, _ in scored) / n
    pred = sum(f for f, _, _ in scored) / n / 100
    bands = []
    for lo, hi in BANDS:
        sel = [(f, a) for f, a, _ in scored if lo <= f < hi]
        if sel:
            bands.append({"band": f"{lo:g}-{hi:g}%" if hi < 100 else f"{lo:g}%+", "n": len(sel),
                          "predicted": sum(f for f, _ in sel) / len(sel),
                          "actual": 100 * sum(a for _, a in sel) / len(sel)})
    top = sorted(scored, key=lambda r: -r[0])[: max(1, n // 10)]
    picks = [(f, a) for f, a, _ in scored if f >= APP_FLOOR]
    out = {
        "sides": n, "predicted": 100 * pred, "actual": 100 * actual, "bands": bands,
        "top10_predicted": sum(f for f, _, _ in top) / len(top),
        "top10_actual": 100 * sum(a for _, a, _ in top) / len(top),
        "picks_n": len(picks),
        "picks_predicted": (sum(f for f, _ in picks) / len(picks)) if picks else None,
        "picks_actual": (100 * sum(a for _, a in picks) / len(picks)) if picks else None,
    }
    p = actual
    out["margin"] = 100 * 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n)
    return out


def report(days=30):
    scored, pending = scored_rows(days)
    s = summarise(scored)
    print(f"Scorecard, last {days} days: predictions logged before kick-off vs results")
    if not s:
        print(f"  no scored games yet ({pending} logged games still waiting for a result)")
        return None
    print(f"  team-sides scored: {s['sides']}  (still waiting for a result: {pending})")
    print(f"  overall FTA: predicted {s['predicted']:.2f}%  actual {s['actual']:.2f}% (±{s['margin']:.2f})")
    print("  band        |     n | predicted | actual")
    for b in s["bands"]:
        print(f"  {b['band']:<11} | {b['n']:>5} | {b['predicted']:>8.2f}% | {b['actual']:>5.2f}%")
    print(f"  top 10%: predicted {s['top10_predicted']:.2f}%  actual {s['top10_actual']:.2f}%")
    if s["picks_n"]:
        print(f"  shown on Picks (>= {APP_FLOOR}%): {s['picks_n']} sides, predicted "
              f"{s['picks_predicted']:.2f}%  actual {s['picks_actual']:.2f}%")
    print("  Small samples swing a lot: a month is a few hundred turnarounds at most.")
    return s
