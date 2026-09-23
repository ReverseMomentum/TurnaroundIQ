import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from tests.feature_config import FEATURE_COLUMNS

MODEL_FILE = PROJECT_ROOT / "fta_model.pkl"
_bundle_cache = None


def _logit(p, eps=1e-6):
    p = np.clip(float(p), eps, 1 - eps)
    return np.log(p / (1 - p))


def load_bundle():
    """Load model bundle or legacy bare XGBClassifier."""
    global _bundle_cache
    if _bundle_cache is not None:
        return _bundle_cache
    if not MODEL_FILE.is_file():
        raise FileNotFoundError(
            f"Model not found at {MODEL_FILE}. Run: python3 -u run.py train"
        )
    obj = joblib.load(MODEL_FILE)
    if isinstance(obj, dict) and "model" in obj:
        _bundle_cache = obj
    else:
        _bundle_cache = {
            "model": obj,
            "calibrator": None,
            "version": "legacy",
            "base_rate": None,
        }
    return _bundle_cache


def load_model():
    return load_bundle()["model"]


def _to_frame(feature_data):
    row = {col: feature_data.get(col) for col in FEATURE_COLUMNS}
    df = pd.DataFrame([row])[FEATURE_COLUMNS]
    for col in FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _calibrate_prob(raw_p, calibrator):
    if calibrator is None:
        return float(np.clip(raw_p, 0.0, 1.0))
    x = np.array([[_logit(raw_p)]])
    return float(np.clip(calibrator.predict_proba(x)[0, 1], 0.0, 1.0))


def predict_fta(feature_data):
    bundle = load_bundle()
    df = _to_frame(feature_data)
    raw = float(bundle["model"].predict_proba(df)[0][1])
    p = _calibrate_prob(raw, bundle.get("calibrator"))
    return round(float(np.clip(p * 100, 0.0, 100.0)), 2)


def predict_with_confidence(feature_data):
    bundle = load_bundle()
    df = _to_frame(feature_data)
    probs = bundle["model"].predict_proba(df)[0]
    raw_fta = float(probs[1])
    fta_probability = _calibrate_prob(raw_fta, bundle.get("calibrator"))
    # Always return percent 0–100 (never a fraction)
    fta_pct = float(np.clip(fta_probability * 100.0, 0.0, 100.0))
    confidence = float(np.clip(max(fta_probability, 1 - fta_probability) * 100.0, 0.0, 100.0))
    return {
        "fta_pct": float(round(fta_pct, 2)),
        "confidence": float(round(confidence, 2)),
        "raw_fta_pct": float(round(np.clip(raw_fta * 100.0, 0.0, 100.0), 2)),
        "model_version": bundle.get("version") or "unknown",
    }


def calculate_ranking_score(expected_profit, fta_pct, xg_edge=0):
    return round((expected_profit * (fta_pct / 100)) + (xg_edge * 0.1), 4)


def get_ev_color(ev_percent):
    if ev_percent >= 100:
        return "green"
    if ev_percent >= 50:
        return "lightgreen"
    if ev_percent >= 0:
        return "orange"
    return "red"


def build_feature_vector(
    team_stats,
    is_home,
    opening_back_odds,
    lead_minute=0,
    max_lead=2,
    odds_movement=None,
    shots_for=0,
    shots_against=0,
    red_cards_for=0,
    red_cards_against=0,
):
    avg_xg = team_stats.get("avg_xg")
    avg_xga = team_stats.get("avg_xga")
    xg_edge = None
    if avg_xg is not None and avg_xga is not None:
        xg_edge = avg_xg - avg_xga

    return {
        "avg_xg": avg_xg,
        "avg_xga": avg_xga,
        "xg_edge": xg_edge,
        "goals_last5": team_stats.get("goals_last5"),
        "conceded_last5": team_stats.get("conceded_last5"),
        "turnaround_pct": team_stats.get("turnaround_pct"),
        "two_up_trigger_rate": team_stats.get("two_up_trigger_rate"),
        "historical_turnaround_rate": team_stats.get("historical_turnaround_rate"),
        "historical_trigger_rate": team_stats.get("historical_trigger_rate"),
        "early_goal_rate": team_stats.get("early_goal_rate"),
        "early_concede_rate": team_stats.get("early_concede_rate"),
        "first_lead_rate": team_stats.get("first_lead_rate"),
        "first_concede_rate": team_stats.get("first_concede_rate"),
        "comeback_rate": team_stats.get("comeback_rate"),
        "lead_retention_rate": team_stats.get("lead_retention_rate"),
        "first_half_goal_diff": team_stats.get("first_half_goal_diff"),
        "second_half_goal_diff": team_stats.get("second_half_goal_diff"),
        "burnout_index": team_stats.get("burnout_index"),
        "league_turnaround_rate": team_stats.get("league_turnaround_rate"),
        "opponent_turnaround_rate": team_stats.get("opponent_turnaround_rate"),
        "live_trigger_rate": team_stats.get("live_trigger_rate"),
        "live_early_goal_rate": team_stats.get("live_early_goal_rate"),
        "live_early_concede_rate": team_stats.get("live_early_concede_rate"),
        "live_first_lead_rate": team_stats.get("live_first_lead_rate"),
        "live_first_concede_rate": team_stats.get("live_first_concede_rate"),
        "live_comeback_rate": team_stats.get("live_comeback_rate"),
        "live_lead_retention_rate": team_stats.get("live_lead_retention_rate"),
        "live_first_half_goal_diff": team_stats.get("live_first_half_goal_diff"),
        "live_second_half_goal_diff": team_stats.get("live_second_half_goal_diff"),
        "live_burnout_index": team_stats.get("live_burnout_index"),
        "trigger_rate_delta": team_stats.get("trigger_rate_delta"),
        "early_goal_delta": team_stats.get("early_goal_delta"),
        "early_concede_delta": team_stats.get("early_concede_delta"),
        "first_lead_delta": team_stats.get("first_lead_delta"),
        "first_concede_delta": team_stats.get("first_concede_delta"),
        "comeback_delta": team_stats.get("comeback_delta"),
        "lead_retention_delta": team_stats.get("lead_retention_delta"),
        "burnout_delta": team_stats.get("burnout_delta"),
        "abs_trigger_delta": team_stats.get("abs_trigger_delta"),
        "abs_retention_delta": team_stats.get("abs_retention_delta"),
        "is_home": int(is_home),
        "lead_minute": lead_minute,
        "max_lead": max_lead,
        "opening_back_odds": opening_back_odds,
        "odds_movement": odds_movement,
        "shots_for": shots_for,
        "shots_against": shots_against,
        "red_cards_for": red_cards_for,
        "red_cards_against": red_cards_against,
    }


def model_version():
    try:
        return load_bundle().get("version") or "V4.1-calibrated"
    except Exception:
        return "V4.1-calibrated"
