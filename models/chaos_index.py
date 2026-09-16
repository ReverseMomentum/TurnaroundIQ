"""
Chaos Index (0–100) — match unpredictability score for its own app segment.

v1 uses team_stats only (comebacks, early goals, triggers, goal volume).
BTTS / O2.5 / red cards / lead-changes can plug in later without API change.
"""

from models.opportunities_engine import get_team_stats


def _pct(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def team_chaos_components(team):
    stats = get_team_stats(team) or {}
    comeback = _pct(stats.get("comeback_rate"))
    live_comeback = _pct(stats.get("live_comeback_rate"))
    comeback_use = live_comeback if live_comeback > 0 else comeback

    early = _pct(stats.get("early_goal_rate"))
    live_early = _pct(stats.get("live_early_goal_rate"))
    early_use = live_early if live_early > 0 else early

    trigger = _pct(stats.get("historical_trigger_rate"))
    live_trigger = _pct(stats.get("live_trigger_rate"))
    two_up = _pct(stats.get("two_up_trigger_rate"))
    trigger_use = max(live_trigger, two_up, trigger)

    goals5 = _pct(stats.get("goals_last5"))
    # last-5 goals → rough per-game ~ /5, scale into 0–100-ish
    goals_component = _clip(goals5 / 5.0 * 40.0)  # 2.5 goals/game → 100 contribution cap later

    retention = _pct(stats.get("lead_retention_rate"))
    # low retention = more chaos
    retention_chaos = _clip(100.0 - retention)

    burnout = _pct(stats.get("burnout_index"))

    return {
        "team": team,
        "comeback": comeback_use,
        "early_goal": early_use,
        "trigger": trigger_use,
        "goals_last5": goals5,
        "goals_component": goals_component,
        "retention_chaos": retention_chaos,
        "burnout": burnout,
    }


def chaos_index(home_team, away_team, league="", kickoff=None, match_id=None):
    h = team_chaos_components(home_team)
    a = team_chaos_components(away_team)

    # Weighted blend → 0–100
    score = (
        0.22 * ((h["comeback"] + a["comeback"]) / 2.0)
        + 0.18 * ((h["early_goal"] + a["early_goal"]) / 2.0)
        + 0.18 * ((h["trigger"] + a["trigger"]) / 2.0)
        + 0.18 * ((h["goals_component"] + a["goals_component"]) / 2.0)
        + 0.14 * ((h["retention_chaos"] + a["retention_chaos"]) / 2.0)
        + 0.10 * min(100.0, (h["burnout"] + a["burnout"]) / 2.0)
    )
    score = round(_clip(score), 1)

    if score >= 75:
        label = "high"
    elif score >= 45:
        label = "medium"
    else:
        label = "low"

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
            "comeback": round((h["comeback"] + a["comeback"]) / 2.0, 1),
            "early_goal": round((h["early_goal"] + a["early_goal"]) / 2.0, 1),
            "trigger": round((h["trigger"] + a["trigger"]) / 2.0, 1),
            "goal_volume": round((h["goals_component"] + a["goals_component"]) / 2.0, 1),
            "lead_instability": round((h["retention_chaos"] + a["retention_chaos"]) / 2.0, 1),
        },
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
