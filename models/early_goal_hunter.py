"""
Early Goal Hunter — last 10 games outweigh long-run team_stats.
"""

from models.opportunities_engine import get_team_stats
from models.form_decay import recent_score_form, blended_rate


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
    recent = recent_score_form(team, n=10)

    prior_early = _pct(stats.get("live_early_goal_rate")) or _pct(stats.get("early_goal_rate"))
    prior_concede = _pct(stats.get("live_early_concede_rate")) or _pct(stats.get("early_concede_rate"))
    prior_first = _pct(stats.get("live_first_lead_rate")) or _pct(stats.get("first_lead_rate"))
    prior_first_concede = _pct(stats.get("live_first_concede_rate")) or _pct(
        stats.get("first_concede_rate")
    )

    early_use = blended_rate(recent.get("early_goal"), prior_early, recent["sample"]) or 0.0
    concede_use = blended_rate(recent.get("early_concede"), prior_concede, recent["sample"]) or 0.0
    first_use = blended_rate(recent.get("scores_first"), prior_first, recent["sample"]) or 0.0
    first_concede_use = blended_rate(
        recent.get("concedes_first"), prior_first_concede, recent["sample"]
    ) or 0.0

    half_diff = _pct(stats.get("first_half_goal_diff"), 0.0)
    p_scores_first = _clip01(first_use / 100.0)
    p_concedes_first = _clip01(first_concede_use / 100.0)
    p_first_half_goal = _clip01(early_use / 100.0 * 0.85 + max(half_diff, 0) * 0.05)
    p_early_concede = _clip01(concede_use / 100.0)

    score = round(100 * (0.55 * p_scores_first + 0.45 * p_first_half_goal), 1)
    return {
        "team": team,
        "p_scores_first": round(p_scores_first, 3),
        "p_concedes_first": round(p_concedes_first, 3),
        "p_first_half_goal": round(p_first_half_goal, 3),
        "p_early_concede": round(p_early_concede, 3),
        "early_goal_rate": early_use,
        "early_concede_rate": concede_use,
        "first_lead_rate": first_use,
        "recent_sample": recent["sample"],
        "hunter_score": score,
    }


def match_early_goal(home_team, away_team, league="", kickoff=None, match_id=None):
    home = team_early_profile(home_team)
    away = team_early_profile(away_team)

    p_1h_any = _clip01(
        1.0 - (1.0 - home["p_first_half_goal"]) * (1.0 - away["p_first_half_goal"])
    )

    raw_h = home["p_scores_first"]
    raw_a = away["p_scores_first"]
    total = raw_h + raw_a
    if total > 0:
        p_home_first = raw_h / total
        p_away_first = raw_a / total
    else:
        p_home_first = p_away_first = 0.5

    away_first_home_leak = round(
        _clip01(0.55 * p_away_first + 0.45 * home["p_early_concede"]), 3
    )
    home_first_away_leak = round(
        _clip01(0.55 * p_home_first + 0.45 * away["p_early_concede"]), 3
    )

    hunter_score = round(
        100
        * (
            0.40 * p_1h_any
            + 0.25 * max(raw_h, raw_a)
            + 0.20 * abs(raw_h - raw_a)
            + 0.15 * max(away_first_home_leak, home_first_away_leak)
        ),
        1,
    )

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
        "away_first_home_leak": away_first_home_leak,
        "home_first_away_leak": home_first_away_leak,
        "home": home,
        "away": away,
        "hunter_score": hunter_score,
        "feature": "early_goal_hunter",
    }


def rank_early_goal_matches(fixtures):
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
