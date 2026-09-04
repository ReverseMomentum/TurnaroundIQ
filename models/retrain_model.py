import joblib
import pandas as pd

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

from database import (
    get_db,
    save_model_run
)

from tests.feature_config import FEATURE_COLUMNS

MODEL_FILE = "fta_model.pkl"

MODEL_VERSION = "V4.0"

MIN_TRAINING_ROWS = 100


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

    if len(df) < MIN_TRAINING_ROWS:

        print(
            f"Only {len(df)} rows found."
        )

        print(
            f"Need at least {MIN_TRAINING_ROWS} rows."
        )

        return

    for col in FEATURE_COLUMNS:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        else:

            print(
                f"[WARN] feature '{col}' not found in "
                f"training_data - filling as missing. "
                f"Run migrate_live_features.py + "
                f"build_training_data.py if this is "
                f"unexpected."
            )

            df[col] = float("nan")

    y = pd.to_numeric(
        df["full_turnaround"],
        errors="coerce"
    ).fillna(0).astype(int)

    # Deliberately NOT imputing here. XGBoost natively
    # handles NaN at both train and predict time (same
    # split-direction learned for missing values), so an
    # imputer fit only at training time - and never
    # reapplied identically at live prediction time - was
    # a source of train/serve skew. Leaving NaN as NaN
    # keeps behaviour identical in both places.
    X = df[FEATURE_COLUMNS]

    if "sample_weight" in df.columns:

        weights = pd.to_numeric(
            df["sample_weight"],
            errors="coerce"
        ).fillna(1.0)

    else:

        weights = pd.Series(
            1.0,
            index=df.index
        )

    stratify_arg = y

    if y.nunique() < 2 or y.value_counts().min() < 2:

        print(
            "[WARN] Not enough examples in the minority "
            "class to stratify the split - falling back "
            "to a random split. Treat metrics from this "
            "run with extra caution."
        )

        stratify_arg = None

    (
        X_train, X_test,
        y_train, y_test,
        w_train, w_test
    ) = train_test_split(
        X,
        y,
        weights,

        test_size=0.20,
        random_state=42,
        stratify=stratify_arg
    )

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
        y_train,
        sample_weight=w_train
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

    try:

        auc = roc_auc_score(
            y_test,
            probabilities
        )

    except ValueError:

        # only one class present in y_test - AUC undefined
        auc = float("nan")

        print(
            "[WARN] Only one class present in the test "
            "split - ROC AUC is undefined for this run."
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
        "Historical + Live + Divergence features"
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
            FEATURE_COLUMNS,
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
