"""
Chaos Index (0–100) with pie-chart breakdown:
  o2_5, btts, early_goal, instability  (share of score, sum ≈ 100)

BTTS / O2.5 from historical_matches + match_results scores.
Early goal + instability from team_stats rates.
"""

from models.opportunities_engine import get_team_stats
from database import get_db


def _pct(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _score_rates(team):
    """BTTS% and O2.5% for a team from stored finals (0–100)."""
    conn = get_db()
    n = btts = o25 = 0
    try:
        rows = conn.execute(
            """
            SELECT final_home, final_away FROM historical_matches
            WHERE home_team = ? OR away_team = ?
            """,
            (team, team),
        ).fetchall()
        for fh, fa in rows:
            if fh is None or fa is None:
                continue
            n += 1
            if fh > 0 and fa > 0:
                btts += 1
            if (fh + fa) >= 3:
                o25 += 1
    except Exception:
        pass
    try:
        rows = conn.execute(
            """
            SELECT final_home, final_away FROM match_results
            WHERE home_team = ? OR away_team = ?
            """,
            (team, team),
        ).fetchall()
        for fh, fa in rows:
            if fh is None or fa is None:
                continue
            n += 1
            if fh > 0 and fa > 0:
                btts += 1
            if (fh + fa) >= 3:
                o25 += 1
    except Exception:
        pass
    conn.close()
    if n <= 0:
        return {"sample": 0, "btts": 50.0, "o2_5": 50.0}
    return {
        "sample": n,
        "btts": round(100.0 * btts / n, 1),
        "o2_5": round(100.0 * o25 / n, 1),
    }


def team_chaos_components(team):
    stats = get_team_stats(team) or {}
    scores = _score_rates(team)

    early = _pct(stats.get("early_goal_rate"))
    live_early = _pct(stats.get("live_early_goal_rate"))
    early_use = live_early if live_early > 0 else early

    comeback = _pct(stats.get("comeback_rate"))
    live_comeback = _pct(stats.get("live_comeback_rate"))
    comeback_use = live_comeback if live_comeback > 0 else comeback

    retention = _pct(stats.get("lead_retention_rate"))
    retention_chaos = _clip(100.0 - retention)

    trigger = max(
        _pct(stats.get("live_trigger_rate")),
        _pct(stats.get("two_up_trigger_rate")),
        _pct(stats.get("historical_trigger_rate")),
    )

    # Instability blends soft lead holding + comebacks + triggers
    instability = _clip(
        0.45 * retention_chaos + 0.35 * comeback_use + 0.20 * trigger
    )

    return {
        "team": team,
        "btts": scores["btts"],
        "o2_5": scores["o2_5"],
        "early_goal": early_use,
        "instability": round(instability, 1),
        "sample": scores["sample"],
    }


def _pie_shares(o2_5, btts, early_goal, instability):
    """Four slices for the app pie; renormalized to sum 100."""
    raw = {
        "o2_5": max(0.0, o2_5),
        "btts": max(0.0, btts),
        "early_goal": max(0.0, early_goal),
        "instability": max(0.0, instability),
    }
    total = sum(raw.values()) or 1.0
    return {k: round(100.0 * v / total, 1) for k, v in raw.items()}


def chaos_index(home_team, away_team, league="", kickoff=None, match_id=None):
    h = team_chaos_components(home_team)
    a = team_chaos_components(away_team)

    o2_5 = (h["o2_5"] + a["o2_5"]) / 2.0
    btts = (h["btts"] + a["btts"]) / 2.0
    early = (h["early_goal"] + a["early_goal"]) / 2.0
    instability = (h["instability"] + a["instability"]) / 2.0

    # Overall chaos 0–100 (equal-ish blend of the four drivers)
    score = _clip(0.28 * o2_5 + 0.28 * btts + 0.22 * early + 0.22 * instability)
    score = round(score, 1)

    if score >= 75:
        label = "high"
    elif score >= 45:
        label = "medium"
    else:
        label = "low"

    pie = _pie_shares(o2_5, btts, early, instability)

    return {
        "match_id": match_id,
        "match": f"{home_team} vs {away_team}",
        "league": league or "",
        "kickoff": kickoff,
        "home_team": home_team,
        "away_team": away_team,
        "chaos_index": score,
        "chaos_label": label,
        "components": {
            "o2_5": round(o2_5, 1),
            "btts": round(btts, 1),
            "early_goal": round(early, 1),
            "instability": round(instability, 1),
        },
        "pie": pie,
        "home": h,
        "away": a,
        "feature": "chaos_index",
    }


def rank_chaos_matches(fixtures):
    seen = set()
    ranked = []
    for fx in fixtures:
        home = fx.get("home_team")
        away = fx.get("away_team")
        if not home or not away:
            continue
        key = (home, away, fx.get("kickoff") or fx.get("match_id"))
        if key in seen:
            continue
        seen.add(key)
        ranked.append(
            chaos_index(
                home,
                away,
                league=fx.get("league") or "",
                kickoff=fx.get("kickoff"),
                match_id=fx.get("match_id"),
            )
        )
    ranked.sort(key=lambda r: r["chaos_index"], reverse=True)
    return ranked
