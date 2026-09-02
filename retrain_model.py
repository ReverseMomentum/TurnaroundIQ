import joblib
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score
)

from xgboost import XGBClassifier

import sys
from pathlib import Path

sys.path.append(
    str(
        Path(__file__).resolve().parent.parent
    )
)

from database import get_db


from database import (
    get_db,
    save_model_run
)

MODEL_FILE = "fta_model.pkl"

MODEL_VERSION = "V3.0"


def train_model():

    conn = get_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM training_data
        """,
        conn
    )

    conn.close()

    if len(df) < 100:

        print(
            f"Only {len(df)} rows found."
        )

        print(
            "Need at least 100 rows."
        )

        return

    features = [

        "avg_xg",
        "avg_xga",

        "xg_edge",

        "goals_last5",
        "conceded_last5",

        "turnaround_pct",

        "two_up_trigger_rate",

        "historical_turnaround_rate",

        "league_turnaround_rate",

        "opponent_turnaround_rate",

        "is_home",

        "lead_minute",
        "max_lead",

        "opening_back_odds",

        "odds_movement",

        "red_cards_for",
        "red_cards_against",

        "shots_for",
        "shots_against"
    ]

    for col in features:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

    y = pd.to_numeric(
        df["full_turnaround"],
        errors="coerce"
    ).fillna(0)

    X = df[features]

    imputer = SimpleImputer(
        strategy="median"
    )

    X = imputer.fit_transform(
        X
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )

    if "sample_weight" in df.columns:

        weights = pd.to_numeric(
            df["sample_weight"],
            errors="coerce"
        ).fillna(1.0)

        train_weights = (
            weights.iloc[X_train.shape[0] * 0:]
        )

    else:

        train_weights = None

    model = XGBClassifier(

        n_estimators=500,

        max_depth=6,

        learning_rate=0.03,

        subsample=0.9,

        colsample_bytree=0.9,

        random_state=42,

        eval_metric="logloss"
    )

    model.fit(
        X_train,
        y_train
    )

    probabilities = model.predict_proba(
        X_test
    )[:, 1]

    brier = brier_score_loss(
        y_test,
        probabilities
    )

    loss = log_loss(
        y_test,
        probabilities
    )

    auc = roc_auc_score(
        y_test,
        probabilities
    )

    joblib.dump(
        model,
        MODEL_FILE
    )

    save_model_run(

        model_name="FTA_MODEL",

        version=MODEL_VERSION,

        training_rows=len(df),

        brier_score=float(
            brier
        ),

        log_loss=float(
            loss
        ),

        roc_auc=float(
            auc
        ),

        notes=
        "Historical + API Model"
    )

    print(
        f"\nModel saved: {MODEL_FILE}"
    )

    print(
        f"Training rows: {len(df)}"
    )

    print(
        f"Brier Score: {brier:.4f}"
    )

    print(
        f"Log Loss: {loss:.4f}"
    )

    print(
        f"ROC AUC: {auc:.4f}"
    )

    print(
        "\nFeature Importance\n"
    )

    importance = sorted(
        zip(
            features,
            model.feature_importances_
        ),
        key=lambda x: x[1],
        reverse=True
    )

    for feature, score in importance:

        print(
            f"{feature}: {score:.4f}"
        )


if __name__ == "__main__":

    train_model()
