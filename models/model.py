import joblib
import pandas as pd

MODEL_FILE = "fta_model.pkl"


def load_model():
    """
    Load trained FTA model.
    """

    return joblib.load(
        MODEL_FILE
    )


def predict_fta(
    feature_data
):
    """
    Return FTA probability as %
    """

    model = load_model()

    df = pd.DataFrame(
        [feature_data]
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

    df = pd.DataFrame(
        [feature_data]
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
    shots_for=0,
    shots_against=0,
    red_cards_for=0,
    red_cards_against=0
):
    """
    Converts team statistics
    into model input.
    """

    avg_xg = (
        team_stats.get(
            "avg_xg",
            0
        )
    )

    avg_xga = (
        team_stats.get(
            "avg_xga",
            0
        )
    )

    xg_edge = (
        avg_xg -
        avg_xga
    )

    return {

        "avg_xg":
            avg_xg,

        "avg_xga":
            avg_xga,

        "xg_edge":
            xg_edge,

        "goals_last5":
            team_stats.get(
                "goals_last5",
                0
            ),

        "conceded_last5":
            team_stats.get(
                "conceded_last5",
                0
            ),

        "turnaround_pct":
            team_stats.get(
                "turnaround_pct",
                0
            ),

        "historical_turnaround_rate":
            team_stats.get(
                "historical_turnaround_rate",
                0
            ),

        "two_up_trigger_rate":
            team_stats.get(
                "two_up_trigger_rate",
                0
            ),

        "league_turnaround_rate":
            team_stats.get(
                "league_turnaround_rate",
                0
            ),

        "opponent_turnaround_rate":
            team_stats.get(
                "opponent_turnaround_rate",
                0
            ),

        "is_home":
            int(is_home),

        "opening_back_odds":
            opening_back_odds,

        "lead_minute":
            lead_minute,

        "shots_for":
            shots_for,

        "shots_against":
            shots_against,

        "red_cards_for":
            red_cards_for,

        "red_cards_against":
            red_cards_against
    }


def model_version():
    """
    Current deployed model version.
    """

    return "V3.0"
