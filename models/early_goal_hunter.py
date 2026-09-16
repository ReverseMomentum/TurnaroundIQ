"""
Early Goal Hunter — standalone feature segment.

Uses existing team_stats rates (no new model / no pipeline overhaul).
Rates in DB are stored as percents (0–100).
"""

from models.opportunities_engine import get_team_stats


def _pct(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip01(x):
    return max(0.0, min(1.0, x))


def team_early_profile(team):
    stats = get_team_stats(team) or {}
    early = _pct(stats.get("early_goal_rate"))
    live_early = _pct(stats.get("live_early_goal_rate"))
    first_lead = _pct(stats.get("first_lead_rate"))
    live_first = _pct(stats.get("live_first_lead_rate"))
    # Prefer live when present, else historical
    early_use = live_early if live_early > 0 else early
    first_use = live_first if live_first > 0 else first_lead
    # Heuristic: first-half goal intensity from early rate + half goal diff signal
    half_diff = _pct(stats.get("first_half_goal_diff"), 0.0)
    p_scores_first = _clip01(first_use / 100.0)
    p_first_half_goal = _clip01(early_use / 100.0 * 0.85 + max(half_diff, 0) * 0.05)
    score = round(100 * (0.55 * p_scores_first + 0.45 * p_first_half_goal), 1)
    return {
        "team": team,
        "p_scores_first": round(p_scores_first, 3),
        "p_first_half_goal": round(p_first_half_goal, 3),
        "early_goal_rate": early_use,
        "first_lead_rate": first_use,
        "hunter_score": score,
    }


def match_early_goal(home_team, away_team, league="", kickoff=None, match_id=None):
    home = team_early_profile(home_team)
    away = team_early_profile(away_team)
    # P(someone scores first in 1H) ≈ complementary of both quiet
    p_1h_any = _clip01(1.0 - (1.0 - home["p_first_half_goal"]) * (1.0 - away["p_first_half_goal"]))
    # Normalize first-scorer probs so they sum to ~1 among the two
    raw_h = home["p_scores_first"]
    raw_a = away["p_scores_first"]
    total = raw_h + raw_a
    if total > 0:
        p_home_first = raw_h / total
        p_away_first = raw_a / total
    else:
        p_home_first = p_away_first = 0.5
    hunter_score = round(100 * (0.5 * p_1h_any + 0.25 * max(raw_h, raw_a) + 0.25 * abs(raw_h - raw_a)), 1)
    return {
        "match_id": match_id,
        "match": f"{home_team} vs {away_team}",
        "league": league or "",
        "kickoff": kickoff,
        "home_team": home_team,
        "away_team": away_team,
        "p_first_half_goal": round(p_1h_any, 3),
        "p_home_scores_first": round(p_home_first, 3),
        "p_away_scores_first": round(p_away_first, 3),
        "home": home,
        "away": away,
        "hunter_score": hunter_score,
        "feature": "early_goal_hunter",
    }


def rank_early_goal_matches(fixtures):
    """fixtures: list with home_team, away_team, optional league/kickoff/match_id."""
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
            match_early_goal(
                home,
                away,
                league=fx.get("league") or "",
                kickoff=fx.get("kickoff"),
                match_id=fx.get("match_id"),
            )
        )
    ranked.sort(key=lambda r: r["hunter_score"], reverse=True)
    return ranked
