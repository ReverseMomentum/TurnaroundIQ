"""
Mismatch Meter — football underdog / price-vs-strength ranker.

Ranks fixtures where the weaker-priced (or weaker-form) side looks closer
in underlying quality than the market gap implies.

Without odds: pure strength mismatch (form + team_stats).
With back_odds on a side: optional edge_pp vs implied probability.
"""

from models.opportunities_engine import get_team_stats
from models.form_decay import recent_score_form


def _pct(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def team_strength_profile(team):
    """0–100 style strength from recent form + team_stats priors."""
    stats = get_team_stats(team) or {}
    recent = recent_score_form(team, n=10)
    sample = int(recent.get("sample") or 0)

    # Attack / defence proxies from recent scores when available
    gf = _pct(recent.get("gf_avg"), None)
    ga = _pct(recent.get("ga_avg"), None)
    if gf is None:
        gf = _pct(stats.get("goals_last5"), 6.0) / 5.0
    if ga is None:
        ga = _pct(stats.get("conceded_last5"), 6.0) / 5.0

    # Map goals for/against to ~0–100 attack/defence scores
    attack = _clip((gf / 2.2) * 100.0)  # ~2.2 gf/game ≈ 100
    defence = _clip(100.0 - (ga / 2.2) * 100.0)

    retention = _pct(stats.get("live_lead_retention_rate")) or _pct(
        stats.get("lead_retention_rate"), 50.0
    )
    comeback = _pct(stats.get("live_comeback_rate")) or _pct(
        stats.get("comeback_rate"), 20.0
    )
    xg_edge = _pct(stats.get("xg_edge"), 0.0)
    # xg_edge often small; scale gently into 0–100 contribution
    xg_component = _clip(50.0 + xg_edge * 25.0)

    # Win-ish proxy from recent BTTS/O2.5 is weak; use goal diff if present
    gd = None
    if recent.get("gf_avg") is not None and recent.get("ga_avg") is not None:
        gd = recent["gf_avg"] - recent["ga_avg"]
    elif stats.get("goals_last5") is not None and stats.get("conceded_last5") is not None:
        gd = (_pct(stats["goals_last5"]) - _pct(stats["conceded_last5"])) / 5.0
    form_component = _clip(50.0 + (gd or 0.0) * 20.0)

    strength = _clip(
        0.30 * attack
        + 0.30 * defence
        + 0.15 * retention
        + 0.10 * comeback
        + 0.10 * form_component
        + 0.05 * xg_component
    )

    return {
        "team": team,
        "strength": round(strength, 1),
        "attack": round(attack, 1),
        "defence": round(defence, 1),
        "retention": round(retention, 1),
        "comeback": round(comeback, 1),
        "form_component": round(form_component, 1),
        "xg_component": round(xg_component, 1),
        "recent_sample": sample,
        "gf_avg": round(gf, 2) if gf is not None else None,
        "ga_avg": round(ga, 2) if ga is not None else None,
    }


def _implied_prob(decimal_odds):
    try:
        o = float(decimal_odds)
        if o <= 1.01:
            return None
        return 1.0 / o
    except (TypeError, ValueError):
        return None


def match_mismatch(
    home_team,
    away_team,
    league="",
    kickoff=None,
    match_id=None,
    home_odds=None,
    away_odds=None,
):
    """
    Build mismatch view for one fixture.

    pick_side = side the meter leans toward (usually the underdog on quality).
    mismatch_score high => larger quality gap vs price/form hierarchy.
    """
    home = team_strength_profile(home_team)
    away = team_strength_profile(away_team)

    # Home advantage soft bump (~3 strength points)
    home_adj = home["strength"] + 3.0
    away_adj = away["strength"]

    strength_gap = home_adj - away_adj  # + => home stronger on model

    # Market favourite from odds when both present; else from strength
    h_imp = _implied_prob(home_odds)
    a_imp = _implied_prob(away_odds)
    if h_imp is not None and a_imp is not None:
        market_fav_home = h_imp >= a_imp
        market_underdog = away_team if market_fav_home else home_team
        market_favourite = home_team if market_fav_home else away_team
        underdog_implied = a_imp if market_fav_home else h_imp
        favourite_implied = h_imp if market_fav_home else a_imp
        underdog_odds = away_odds if market_fav_home else home_odds
    else:
        market_fav_home = home_adj >= away_adj
        market_underdog = away_team if market_fav_home else home_team
        market_favourite = home_team if market_fav_home else away_team
        underdog_implied = favourite_implied = None
        underdog_odds = None

    underdog_is_home = market_underdog == home_team
    underdog_strength = home_adj if underdog_is_home else away_adj
    favourite_strength = away_adj if underdog_is_home else home_adj

    # Quality gap: how close is the dog relative to the favourite?
    # Positive when underdog is closer/stronger than hierarchy suggests
    quality_gap = underdog_strength - favourite_strength  # often negative

    # Mismatch score: reward dogs that are not far behind (or ahead) on model
    # Map quality_gap (-40..+20 typical) into 0–100
    # Dog 10 pts weaker => moderate; dog equal/stronger => high
    mismatch_raw = 50.0 + quality_gap * 1.8
    # Slight boost when market prices dog long but model is tight
    if underdog_implied is not None and favourite_implied is not None:
        market_gap = favourite_implied - underdog_implied  # large => big fav
        model_gap = (favourite_strength - underdog_strength) / 100.0
        # If market gap >> model gap, mismatch rises
        mismatch_raw += max(0.0, (market_gap - model_gap) * 40.0)

    mismatch_score = round(_clip(mismatch_raw), 1)
    label = "high" if mismatch_score >= 65 else "medium" if mismatch_score >= 45 else "low"

    # Optional edge if we have underdog odds: model win proxy vs implied
    # Crude: softmax-ish from strengths
    total_s = underdog_strength + favourite_strength
    model_p_underdog = underdog_strength / total_s if total_s > 0 else 0.5
    edge_pp = None
    if underdog_implied is not None:
        edge_pp = round(100.0 * (model_p_underdog - underdog_implied), 1)

    return {
        "match_id": match_id,
        "match": f"{home_team} vs {away_team}",
        "league": league or "",
        "kickoff": kickoff,
        "home_team": home_team,
        "away_team": away_team,
        "mismatch_score": mismatch_score,
        "mismatch_label": label,
        "pick_side": market_underdog,
        "pick_is_home": underdog_is_home,
        "market_favourite": market_favourite,
        "market_underdog": market_underdog,
        "strength_gap_home_minus_away": round(strength_gap, 1),
        "underdog_strength": round(underdog_strength, 1),
        "favourite_strength": round(favourite_strength, 1),
        "quality_gap": round(quality_gap, 1),
        "model_p_underdog": round(model_p_underdog, 3),
        "underdog_implied": round(underdog_implied, 3) if underdog_implied else None,
        "underdog_odds": underdog_odds,
        "edge_pp": edge_pp,
        "home": home,
        "away": away,
        "feature": "mismatch_meter",
        "note": (
            "Ranking signal: underdog quality vs hierarchy. "
            "edge_pp only when odds present; not a guaranteed +EV claim."
        ),
    }


def rank_mismatch_matches(fixtures):
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
            match_mismatch(
                home,
                away,
                league=fx.get("league") or "",
                kickoff=fx.get("kickoff"),
                match_id=fx.get("match_id"),
                home_odds=fx.get("home_odds") or fx.get("back_odds") if fx.get("team") == home else fx.get("home_odds"),
                away_odds=fx.get("away_odds"),
            )
        )
    ranked.sort(key=lambda r: r["mismatch_score"], reverse=True)
    return ranked
