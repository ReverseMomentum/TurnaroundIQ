import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db, get_odds_movement
from calculations import (
    calculate_lay_stake,
    calculate_liability,
    calculate_qualifying_loss,
    calculate_fta_profit,
    calculate_expected_profit,
    calculate_ev_percent,
    calculate_ev_rating,
    calculate_ranking_score,
)
from models.model import predict_with_confidence, build_feature_vector

TEAM_STATS_COLUMNS = [
    "avg_xg", "avg_xga", "xg_edge",
    "goals_last5", "conceded_last5",
    "turnaround_pct", "two_up_trigger_rate",
    "historical_turnaround_rate", "historical_trigger_rate",
    "early_goal_rate", "early_concede_rate",
    "first_lead_rate", "first_concede_rate",
    "comeback_rate", "lead_retention_rate",
    "first_half_goal_diff", "second_half_goal_diff",
    "burnout_index",
    "league_turnaround_rate", "opponent_turnaround_rate",
    "live_trigger_rate", "live_early_goal_rate", "live_early_concede_rate",
    "live_first_lead_rate", "live_first_concede_rate",
    "live_comeback_rate", "live_lead_retention_rate",
    "live_first_half_goal_diff", "live_second_half_goal_diff",
    "live_burnout_index",
    "trigger_rate_delta", "early_goal_delta", "early_concede_delta",
    "first_lead_delta", "first_concede_delta", "comeback_delta",
    "lead_retention_delta", "burnout_delta",
    "abs_trigger_delta", "abs_retention_delta",
]

# Display / paper bands (fta_pct as percent 0–100)
FTA_BANDS = [
    ("elite_12plus", 12.0, 100.0),
    ("high_8_12", 8.0, 12.0),
    ("mid_5_8", 5.0, 8.0),
    ("low_3_5", 3.0, 5.0),
    ("micro_under_3", 0.0, 3.0),
]

# Default edge gate: model FTA% must clear implied% + this buffer
DEFAULT_EDGE_BUFFER_PP = 2.0

_last_rank_errors = []


def get_last_rank_errors():
    return list(_last_rank_errors)


def fta_pct_as_percent(val) -> float:
    try:
        p = float(val or 0)
    except (TypeError, ValueError):
        return 0.0
    if 0 < p <= 1.0:
        return p * 100.0
    return p


def fta_band(val) -> str:
    pct = fta_pct_as_percent(val)
    for name, lo, hi in FTA_BANDS:
        if lo <= pct < hi or (hi >= 100 and pct >= lo):
            return name
    return "micro_under_3"


def implied_pct_from_odds(decimal_odds):
    """Treat decimal odds as a crude fair price for the offered outcome."""
    try:
        o = float(decimal_odds)
        if o <= 1.01:
            return None
        return round(100.0 / o, 2)
    except (TypeError, ValueError):
        return None


def edge_pp(fta_pct, back_odds):
    """
    Model FTA% minus implied% from back odds.
    Positive => model is more bullish than the price.
    Only meaningful when odds are real (not default estimated).
    """
    imp = implied_pct_from_odds(back_odds)
    if imp is None:
        return None
    return round(fta_pct_as_percent(fta_pct) - imp, 2)


def passes_edge_gate(fta_pct, back_odds, buffer_pp=DEFAULT_EDGE_BUFFER_PP, require_real_odds=False, odds_estimated=False):
    """
    True if model clears implied + buffer.
    If require_real_odds and odds are estimated → fail the gate.
    """
    if require_real_odds and odds_estimated:
        return False
    e = edge_pp(fta_pct, back_odds)
    if e is None:
        return False
    return e >= float(buffer_pp)


def estimate_lay_odds(back_odds):
    if back_odds < 2:
        margin = 0.03
    elif back_odds < 5:
        margin = 0.05
    else:
        margin = 0.08
    return round(back_odds * (1 + margin), 2)


def _rate(value):
    """Coerce a stored rate to float percent, or None if missing."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def resolve_two_up_pct(stats):
    """Prefer live two_up_trigger_rate, else historical_trigger_rate."""
    for key in ("two_up_trigger_rate", "live_trigger_rate", "historical_trigger_rate"):
        v = _rate(stats.get(key))
        if v is not None and v > 0:
            return v, key
    return 0.0, None


def resolve_turnaround_pct(stats):
    """Prefer live turnaround_pct, else historical_turnaround_rate."""
    for key in ("turnaround_pct", "historical_turnaround_rate"):
        v = _rate(stats.get(key))
        if v is not None and v > 0:
            return v, key
    return 0.0, None


def get_team_stats(team):
    if not team:
        return {c: None for c in TEAM_STATS_COLUMNS}
    conn = get_db()
    try:
        columns_sql = ", ".join(TEAM_STATS_COLUMNS)
        row = conn.execute(
            f"SELECT {columns_sql} FROM team_stats WHERE team = ?",
            (team,),
        ).fetchone()
        conn.close()
        if row:
            stats = dict(zip(TEAM_STATS_COLUMNS, row))
            if not _rate(stats.get("two_up_trigger_rate")):
                hist = _rate(stats.get("historical_trigger_rate"))
                if hist:
                    stats["two_up_trigger_rate"] = hist
            if not _rate(stats.get("turnaround_pct")):
                hist = _rate(stats.get("historical_turnaround_rate"))
                if hist:
                    stats["turnaround_pct"] = hist
            return stats
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
    return {c: None for c in TEAM_STATS_COLUMNS}


def build_opportunity(fixture, stake=40, commission=2):
    team = fixture.get("team") or fixture.get("home_team")
    if not team:
        raise ValueError("fixture missing team")

    stats = get_team_stats(team)
    back_odds = float(fixture.get("back_odds") or 2.1)
    odds_estimated = bool(fixture.get("odds_estimated"))

    supplied_lay = fixture.get("lay_odds")
    if supplied_lay is None:
        lay_odds = estimate_lay_odds(back_odds)
        estimated_lay = True
    else:
        lay_odds = float(supplied_lay)
        estimated_lay = False

    home_team = fixture.get("home_team")
    away_team = fixture.get("away_team")
    opening_back_odds = None
    odds_movement = None
    if home_team and away_team:
        try:
            opening_back_odds, odds_movement = get_odds_movement(
                home_team, away_team, team
            )
        except Exception:
            pass

    feature_vector = build_feature_vector(
        team_stats=stats,
        is_home=fixture.get("is_home", True),
        opening_back_odds=opening_back_odds if opening_back_odds is not None else back_odds,
        odds_movement=odds_movement,
        lead_minute=0,
        max_lead=2,
        shots_for=0,
        shots_against=0,
        red_cards_for=0,
        red_cards_against=0,
    )

    prediction = predict_with_confidence(feature_vector)
    fta_pct = float(prediction["fta_pct"])
    confidence = float(prediction["confidence"])

    two_up_pct, two_up_source = resolve_two_up_pct(stats)
    turnaround_pct, turnaround_source = resolve_turnaround_pct(stats)
    joint_pct = (two_up_pct * turnaround_pct) / 100.0 if two_up_pct and turnaround_pct else 0.0

    lay_stake = calculate_lay_stake(back_odds, lay_odds, stake, commission)
    liability = calculate_liability(lay_odds, lay_stake)
    qualifying_loss = calculate_qualifying_loss(
        back_odds, lay_odds, stake, lay_stake, commission
    )
    ql_percent = (abs(qualifying_loss) / stake) * 100 if stake else 0
    fta_profit = calculate_fta_profit(stake, back_odds, lay_stake, commission)
    expected_profit = calculate_expected_profit(fta_profit, qualifying_loss, fta_pct)
    ev_percent = calculate_ev_percent(expected_profit, qualifying_loss)
    ev_rating = calculate_ev_rating(fta_pct, qualifying_loss, stake)
    ranking_score = calculate_ranking_score(expected_profit, fta_pct)

    fta_display = fta_pct_as_percent(fta_pct)
    band = fta_band(fta_display)
    implied = implied_pct_from_odds(back_odds)
    e_pp = edge_pp(fta_display, back_odds)
    # Soft gate for display (does not require real odds by default)
    gate_soft = passes_edge_gate(
        fta_display, back_odds, buffer_pp=DEFAULT_EDGE_BUFFER_PP,
        require_real_odds=False, odds_estimated=odds_estimated,
    )
    gate_strict = passes_edge_gate(
        fta_display, back_odds, buffer_pp=DEFAULT_EDGE_BUFFER_PP,
        require_real_odds=True, odds_estimated=odds_estimated,
    )

    return {
        "match": fixture.get("match") or f"{home_team} vs {away_team}",
        "team": team,
        "league": fixture.get("league") or "",
        "bookmaker": fixture.get("bookmaker") or "",
        "back_odds": round(back_odds, 2),
        "lay_odds": round(lay_odds, 2),
        "estimated_lay": estimated_lay,
        "odds_estimated": odds_estimated,
        "stake": stake,
        "commission": commission,
        "fta_pct": round(fta_display, 2),
        "fta_band": band,
        "confidence": round(confidence, 2),
        "two_up_pct": round(two_up_pct, 2),
        "turnaround_pct": round(turnaround_pct, 2),
        "joint_pct": round(joint_pct, 2),
        "two_up_source": two_up_source,
        "turnaround_source": turnaround_source,
        "implied_pct": implied,
        "edge_pp": e_pp,
        "passes_edge_gate": gate_soft,
        "passes_strict_edge_gate": gate_strict,
        "edge_note": (
            "edge_pp = model FTA% − 100/odds. Meaningful only with real odds; "
            "estimated default odds are not a true FTA market."
        ),
        "lay_stake": round(lay_stake, 2),
        "liability": round(liability, 2),
        "qualifying_loss": round(qualifying_loss, 2),
        "ql_percent": round(ql_percent, 2),
        "fta_profit": round(fta_profit, 2),
        "expected_profit": round(expected_profit, 2),
        "ev_percent": round(ev_percent, 2),
        "ev_rating": round(ev_rating, 2),
        "ranking_score": round(ranking_score, 4),
        "home_team": home_team,
        "away_team": away_team,
        "kickoff": fixture.get("kickoff"),
        "product": "fta",
    }


def rebuild_opportunity(opportunity, lay_odds, commission):
    back_odds = opportunity["back_odds"]
    stake = opportunity["stake"]
    lay_stake = calculate_lay_stake(back_odds, lay_odds, stake, commission)
    liability = calculate_liability(lay_odds, lay_stake)
    qualifying_loss = calculate_qualifying_loss(
        back_odds, lay_odds, stake, lay_stake, commission
    )
    ql_percent = (abs(qualifying_loss) / stake) * 100 if stake else 0
    fta_profit = calculate_fta_profit(stake, back_odds, lay_stake, commission)
    expected_profit = calculate_expected_profit(
        fta_profit, qualifying_loss, opportunity["fta_pct"]
    )
    ev_percent = calculate_ev_percent(expected_profit, qualifying_loss)
    ev_rating = calculate_ev_rating(opportunity["fta_pct"], qualifying_loss, stake)
    updated = dict(opportunity)
    updated["lay_odds"] = round(lay_odds, 2)
    updated["commission"] = commission
    updated["estimated_lay"] = False
    updated["odds_estimated"] = False
    updated["lay_stake"] = round(lay_stake, 2)
    updated["liability"] = round(liability, 2)
    updated["qualifying_loss"] = round(qualifying_loss, 2)
    updated["ql_percent"] = round(ql_percent, 2)
    updated["fta_profit"] = round(fta_profit, 2)
    updated["expected_profit"] = round(expected_profit, 2)
    updated["ev_percent"] = round(ev_percent, 2)
    updated["ev_rating"] = round(ev_rating, 2)
    # refresh edge with real odds
    fta = fta_pct_as_percent(updated.get("fta_pct"))
    updated["implied_pct"] = implied_pct_from_odds(back_odds)
    updated["edge_pp"] = edge_pp(fta, back_odds)
    updated["passes_edge_gate"] = passes_edge_gate(
        fta, back_odds, require_real_odds=False, odds_estimated=False
    )
    updated["passes_strict_edge_gate"] = passes_edge_gate(
        fta, back_odds, require_real_odds=True, odds_estimated=False
    )
    updated["fta_band"] = fta_band(fta)
    return updated


def rank_opportunities(fixtures):
    global _last_rank_errors
    opportunities = []
    _last_rank_errors = []
    for fixture in fixtures:
        try:
            opportunity = build_opportunity(fixture)
            if opportunity:
                opportunities.append(opportunity)
        except Exception as exc:
            if len(_last_rank_errors) < 5:
                _last_rank_errors.append({
                    "team": fixture.get("team"),
                    "match": fixture.get("match"),
                    "error": f"{type(exc).__name__}: {exc}",
                })
            continue
    opportunities.sort(
        key=lambda x: (float(x.get("fta_pct") or 0), float(x.get("joint_pct") or 0)),
        reverse=True,
    )
    return opportunities


def filter_opportunities(
    opportunities,
    min_fta=None,
    min_edge_pp=None,
    band=None,
    require_real_odds=False,
    edge_gate_only=False,
):
    """Post-rank selectivity for hardened FTA surface."""
    out = []
    for o in opportunities:
        fta = fta_pct_as_percent(o.get("fta_pct"))
        if min_fta is not None and fta < float(min_fta):
            continue
        if band and (o.get("fta_band") or fta_band(fta)) != band:
            continue
        if require_real_odds and o.get("odds_estimated"):
            continue
        if min_edge_pp is not None:
            e = o.get("edge_pp")
            if e is None or float(e) < float(min_edge_pp):
                continue
        if edge_gate_only:
            if require_real_odds:
                if not o.get("passes_strict_edge_gate"):
                    continue
            elif not o.get("passes_edge_gate"):
                continue
        out.append(o)
    return out


def get_top_opportunities(fixtures, limit=20):
    return rank_opportunities(fixtures)[:limit]
