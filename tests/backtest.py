"""
Backtest the FTA model against training_data.

Two separate things are reported, deliberately kept apart:

1. Model quality (Brier/log loss/AUC + calibration table) -
   this only needs predicted probability vs actual outcome,
   no odds required, and is trustworthy for every row.

2. Monetary simulation (staking, P&L, ROI) - this NEEDS real
   back/lay odds. Right now most historical rows have no
   captured odds (odds_history only has coverage for fixtures
   odds_collector.py was polling live before kickoff), so rows
   without real opening_back_odds fall back to a flat synthetic
   price for illustration only. The script tells you the real
   coverage % up front - treat the monetary numbers as a sanity
   check until that coverage is high, not as a real edge estimate.

Usage:
    python backtest.py
    python backtest.py --ev-rating 100 --stake 40 --commission 2
"""

import argparse

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

from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score
)

from database import get_db
from feature_config import FEATURE_COLUMNS

from calculations import (
    calculate_lay_stake,
    calculate_qualifying_loss,
    calculate_fta_profit,
    calculate_expected_profit,
    calculate_ev_rating
)

from opportunities_engine import estimate_lay_odds

MODEL_FILE = "fta_model.pkl"

DEFAULT_STAKE = 40
DEFAULT_COMMISSION = 2
DEFAULT_EV_RATING_THRESHOLD = 100

# Only used when a row has no real captured opening_back_odds.
# This is clearly flagged in the output - it is NOT a real
# market price, just a placeholder so the monetary simulation
# can still run on rows without odds coverage.
SYNTHETIC_BACK_ODDS = 1.85

TRADES_OUTPUT_FILE = "backtest_trades.csv"


def load_training_data():

    conn = get_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM training_data
        """,
        conn
    )

    conn.close()

    return df


def prepare_features(
    df
):

    for col in FEATURE_COLUMNS:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        else:

            df[col] = float("nan")

    return df[FEATURE_COLUMNS]


def report_model_quality(
    df,
    probabilities
):

    y = pd.to_numeric(
        df["full_turnaround"],
        errors="coerce"
    ).fillna(0).astype(int)

    print(
        "\n"
        + "=" * 60
    )

    print(
        "MODEL QUALITY (all historical rows)"
    )

    print(
        "=" * 60
    )

    try:

        print(
            f"Brier Score: "
            f"{brier_score_loss(y, probabilities):.4f}"
        )

        print(
            f"Log Loss:    "
            f"{log_loss(y, probabilities):.4f}"
        )

        print(
            f"ROC AUC:     "
            f"{roc_auc_score(y, probabilities):.4f}"
        )

    except ValueError as exc:

        print(
            f"Could not compute one or more metrics "
            f"(likely only one outcome class present "
            f"in the data): {exc}"
        )

    calibration_df = pd.DataFrame(
        {
            "predicted_fta_pct":
                probabilities * 100,

            "actual_turnaround":
                y
        }
    )

    try:

        calibration_df["bucket"] = pd.qcut(
            calibration_df["predicted_fta_pct"],
            10,
            duplicates="drop"
        )

        calibration = (
            calibration_df
            .groupby(
                "bucket",
                observed=True
            )
            .agg(
                predicted_avg=(
                    "predicted_fta_pct",
                    "mean"
                ),
                actual_pct=(
                    "actual_turnaround",
                    "mean"
                ),
                n=(
                    "actual_turnaround",
                    "count"
                )
            )
        )

        calibration["actual_pct"] = (
            calibration["actual_pct"] * 100
        )

        print(
            "\nCalibration by decile "
            "(predicted vs actual FTA %):\n"
        )

        print(
            calibration.round(2).to_string()
        )

    except ValueError:

        print(
            "\nNot enough rows / variation to build a "
            "calibration table yet - collect more data."
        )


def run_backtest(
    ev_rating_threshold=DEFAULT_EV_RATING_THRESHOLD,
    stake=DEFAULT_STAKE,
    commission=DEFAULT_COMMISSION
):

    df = load_training_data()

    if len(df) == 0:

        print(
            "No rows in training_data - run "
            "build_training_data.py first."
        )

        return

    try:

        model = joblib.load(
            MODEL_FILE
        )

    except FileNotFoundError:

        print(
            f"No model file found at {MODEL_FILE} - "
            f"run retrain_model.py first."
        )

        return

    X = prepare_features(
        df
    )

    probabilities = model.predict_proba(
        X
    )[:, 1]

    df = df.copy()

    df["predicted_fta_pct"] = (
        probabilities * 100
    )

    report_model_quality(
        df,
        probabilities
    )

    # ------------------------------------
    # Monetary simulation
    # ------------------------------------

    print(
        "\n"
        + "=" * 60
    )

    print(
        "MONETARY SIMULATION"
    )

    print(
        "=" * 60
    )

    has_real_odds = (
        "opening_back_odds" in df.columns
        and df["opening_back_odds"].notna()
    )

    real_odds_count = (
        int(has_real_odds.sum())
        if "opening_back_odds" in df.columns
        else 0
    )

    print(
        f"{real_odds_count}/{len(df)} rows have real "
        f"captured odds. Rows without them use a flat "
        f"synthetic back_odds={SYNTHETIC_BACK_ODDS} for "
        f"illustration only."
    )

    if real_odds_count < len(df):

        print(
            "Treat monetary results as a sanity check "
            "until real odds coverage is higher - they "
            "are NOT a real edge estimate yet."
        )

    trades = []

    for _, row in df.iterrows():

        opening_odds = row.get(
            "opening_back_odds"
        )

        if pd.notna(opening_odds) and opening_odds > 1:

            back_odds = float(
                opening_odds
            )

            odds_are_real = True

        else:

            back_odds = SYNTHETIC_BACK_ODDS

            odds_are_real = False

        lay_odds = estimate_lay_odds(
            back_odds
        )

        lay_stake = calculate_lay_stake(
            back_odds,
            lay_odds,
            stake,
            commission
        )

        qualifying_loss = calculate_qualifying_loss(
            back_odds,
            lay_odds,
            stake,
            lay_stake,
            commission
        )

        fta_profit = calculate_fta_profit(
            stake,
            back_odds,
            lay_stake,
            commission
        )

        fta_pct = row[
            "predicted_fta_pct"
        ]

        ev_rating = calculate_ev_rating(
            fta_pct,
            qualifying_loss,
            stake
        )

        if ev_rating < ev_rating_threshold:

            continue

        actual_won = bool(
            row.get(
                "full_turnaround",
                0
            )
        )

        actual_profit = (
            fta_profit
            if actual_won
            else qualifying_loss
        )

        trades.append(
            {
                "match_id": row.get("match_id"),
                "league": row.get("league"),
                "team": row.get("team"),
                "predicted_fta_pct": round(fta_pct, 2),
                "ev_rating": round(ev_rating, 2),
                "back_odds": round(back_odds, 2),
                "odds_are_real": odds_are_real,
                "stake": stake,
                "actual_won": actual_won,
                "actual_profit": round(actual_profit, 2)
            }
        )

    if not trades:

        print(
            f"\nNo opportunities cleared "
            f"ev_rating >= {ev_rating_threshold}. "
            f"Try a lower --ev-rating threshold, or "
            f"collect more data first."
        )

        return

    trades_df = pd.DataFrame(
        trades
    )

    total_staked = trades_df["stake"].sum()

    total_profit = trades_df["actual_profit"].sum()

    win_rate = (
        trades_df["actual_won"].mean() * 100
    )

    roi = (
        (total_profit / total_staked) * 100
        if total_staked
        else 0
    )

    real_odds_trades = int(
        trades_df["odds_are_real"].sum()
    )

    print(
        f"\nBets taken (ev_rating >= "
        f"{ev_rating_threshold}): {len(trades_df)}"
    )

    print(
        f"  - using real captured odds: {real_odds_trades}"
    )

    print(
        f"  - using synthetic placeholder odds: "
        f"{len(trades_df) - real_odds_trades}"
    )

    print(
        f"\nWin rate:     {win_rate:.2f}%"
    )

    print(
        f"Total staked: {total_staked:.2f}"
    )

    print(
        f"Total profit: {total_profit:.2f}"
    )

    print(
        f"ROI:          {roi:.2f}%"
    )

    trades_df.to_csv(
        TRADES_OUTPUT_FILE,
        index=False
    )

    print(
        f"\nTrade-level detail written to "
        f"{TRADES_OUTPUT_FILE}"
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Backtest the FTA model against "
            "training_data."
        )
    )

    parser.add_argument(
        "--ev-rating",
        type=float,
        default=DEFAULT_EV_RATING_THRESHOLD,
        help=(
            "Minimum ev_rating for a historical row to "
            "count as a bet the strategy would have "
            "taken. 100 means FTA%% == qualifying-loss%%; "
            "above 100 is theoretically +EV."
        )
    )

    parser.add_argument(
        "--stake",
        type=float,
        default=DEFAULT_STAKE
    )

    parser.add_argument(
        "--commission",
        type=float,
        default=DEFAULT_COMMISSION
    )

    args = parser.parse_args()

    run_backtest(
        ev_rating_threshold=args.ev_rating,
        stake=args.stake,
        commission=args.commission
    )
