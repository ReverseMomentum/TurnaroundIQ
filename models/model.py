import sys
from pathlib import Path

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(
        str(PROJECT_ROOT)
    )

import joblib
import pandas as pd

from tests.feature_config import FEATURE_COLUMNS

MODEL_FILE = "fta_model.pkl"


def load_model():
    """
    Load trained FTA model.
    """

    return joblib.load(
        MODEL_FILE
    )


def _to_frame(
    feature_data
):
    """
    Build a single-row DataFrame with columns in the exact
    order the model was trained on. Any feature not present
    in feature_data is left as NaN (XGBoost handles this
    natively, matching how training treats missing values -
    see retrain_model.py) rather than silently defaulting to
    0, which would misrepresent a real missing value as a
    real zero.
    """

    row = {
        col: feature_data.get(col)
        for col in FEATURE_COLUMNS
    }

    return pd.DataFrame(
        [row]
    )[FEATURE_COLUMNS]


def predict_fta(
    feature_data
):
    """
    Return FTA probability as %
    """

    model = load_model()

    df = _to_frame(
        feature_data
    )

    probability = (
        model
        .predict_proba(df)[0][1]
    )

    return round(
        probability * 100,
        2
    )


def predict_with_confidence(
    feature_data
):
    """
    Return FTA percentage
    and confidence score.
    """

    model = load_model()

    df = _to_frame(
        feature_data
    )

    probabilities = (
        model
        .predict_proba(df)[0]
    )

    fta_probability = (
        probabilities[1]
    )

    confidence = (
        max(probabilities)
        * 100
    )

    return {
        "fta_pct": round(
            fta_probability * 100,
            2
        ),
        "confidence": round(
            confidence,
            2
        )
    }


def calculate_ranking_score(
    expected_profit,
    fta_pct,
    xg_edge=0
):
    """
    Opportunity ranking score.

    Higher is better.
    """

    return round(
        (
            expected_profit
            *
            (
                fta_pct / 100
            )
        )
        +
        (
            xg_edge * 0.1
        ),
        4
    )


def get_ev_color(
    ev_percent
):
    """
    UI colour helper.
    """

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
    red_cards_against=0
):
    """
    Converts team statistics into model input.

    team_stats is expected to be a dict pulled from the
    team_stats table (see opportunities_engine.get_team_stats)
    covering both the historical/live rate columns and the
    divergence columns. Any key not present in team_stats is
    left as None -> NaN, matching how retrain_model.py treats
    genuinely missing data (rather than a misleading 0).
    """

    avg_xg = team_stats.get(
        "avg_xg"
    )

    avg_xga = team_stats.get(
        "avg_xga"
    )

    xg_edge = None

    if (
        avg_xg is not None
        and avg_xga is not None
    ):

        xg_edge = avg_xg - avg_xga

    vector = {

        "avg_xg": avg_xg,
        "avg_xga": avg_xga,
        "xg_edge": xg_edge,

        "goals_last5":
            team_stats.get("goals_last5"),
        "conceded_last5":
            team_stats.get("conceded_last5"),

        "turnaround_pct":
            team_stats.get("turnaround_pct"),
        "two_up_trigger_rate":
            team_stats.get("two_up_trigger_rate"),

        "historical_turnaround_rate":
            team_stats.get("historical_turnaround_rate"),
        "historical_trigger_rate":
            team_stats.get("historical_trigger_rate"),

        "early_goal_rate":
            team_stats.get("early_goal_rate"),
        "early_concede_rate":
            team_stats.get("early_concede_rate"),

        "first_lead_rate":
            team_stats.get("first_lead_rate"),
        "first_concede_rate":
            team_stats.get("first_concede_rate"),

        "comeback_rate":
            team_stats.get("comeback_rate"),
        "lead_retention_rate":
            team_stats.get("lead_retention_rate"),

        "first_half_goal_diff":
            team_stats.get("first_half_goal_diff"),
        "second_half_goal_diff":
            team_stats.get("second_half_goal_diff"),

        "burnout_index":
            team_stats.get("burnout_index"),

        "league_turnaround_rate":
            team_stats.get("league_turnaround_rate"),
        "opponent_turnaround_rate":
            team_stats.get("opponent_turnaround_rate"),

        "live_trigger_rate":
            team_stats.get("live_trigger_rate"),
        "live_early_goal_rate":
            team_stats.get("live_early_goal_rate"),
        "live_early_concede_rate":
            team_stats.get("live_early_concede_rate"),
        "live_first_lead_rate":
            team_stats.get("live_first_lead_rate"),
        "live_first_concede_rate":
            team_stats.get("live_first_concede_rate"),
        "live_comeback_rate":
            team_stats.get("live_comeback_rate"),
        "live_lead_retention_rate":
            team_stats.get("live_lead_retention_rate"),
        "live_first_half_goal_diff":
            team_stats.get("live_first_half_goal_diff"),
        "live_second_half_goal_diff":
            team_stats.get("live_second_half_goal_diff"),
        "live_burnout_index":
            team_stats.get("live_burnout_index"),

        "trigger_rate_delta":
            team_stats.get("trigger_rate_delta"),
        "early_goal_delta":
            team_stats.get("early_goal_delta"),
        "early_concede_delta":
            team_stats.get("early_concede_delta"),
        "first_lead_delta":
            team_stats.get("first_lead_delta"),
        "first_concede_delta":
            team_stats.get("first_concede_delta"),
        "comeback_delta":
            team_stats.get("comeback_delta"),
        "lead_retention_delta":
            team_stats.get("lead_retention_delta"),
        "burnout_delta":
            team_stats.get("burnout_delta"),

        "abs_trigger_delta":
            team_stats.get("abs_trigger_delta"),
        "abs_retention_delta":
            team_stats.get("abs_retention_delta"),

        "is_home":
            int(is_home),

        "lead_minute":
            lead_minute,
        "max_lead":
            max_lead,

        "opening_back_odds":
            opening_back_odds,
        "odds_movement":
            odds_movement,

        "shots_for":
            shots_for,
        "shots_against":
            shots_against,

        "red_cards_for":
            red_cards_for,
        "red_cards_against":
            red_cards_against
    }

    return vector


def model_version():
    """
    Current deployed model version.
    """

    return "V4.0"
