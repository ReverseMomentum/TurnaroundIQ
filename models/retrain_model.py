"""
Train FTA classifier with imbalance handling + Platt calibration.

Saves a bundle to fta_model.pkl:
  {
    "model": XGBClassifier,
    "calibrator": LogisticRegression | None,  # Platt on logit(p)
    "version": str,
    "base_rate": float,
  }

Also writes model_runs + feature_importance rows for long-term tracking.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db
from models.importance_store import save_model_run_with_importance
from tests.feature_config import FEATURE_COLUMNS

MODEL_FILE = Path(__file__).resolve().parent.parent / "fta_model.pkl"
MODEL_VERSION = "V4.1-calibrated"
MIN_TRAINING_ROWS = 100


def _logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _fit_platt(raw_probs, y):
    y = np.asarray(y).astype(int)
    if y.sum() < 5 or (len(y) - y.sum()) < 5:
        print("[WARN] Too few positives/negatives for Platt — skipping calibration")
        return None

    x = _logit(np.asarray(raw_probs, dtype=float)).reshape(-1, 1)
    cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    cal.fit(x, y)
    return cal


def _apply_platt(calibrator, raw_probs):
    if calibrator is None:
        return np.asarray(raw_probs, dtype=float)
    x = _logit(np.asarray(raw_probs, dtype=float)).reshape(-1, 1)
    return calibrator.predict_proba(x)[:, 1]


def _reliability_table(y, p, n_bins=8):
    y = np.asarray(y).astype(float)
    p = np.asarray(p).astype(float)
    edges = np.linspace(0, max(float(p.max()), 1e-6), n_bins + 1)
    print("\nReliability (pred mean → actual rate, n)")
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi if i < n_bins - 1 else p <= hi)
        if mask.sum() == 0:
            continue
        print(
            f"  [{lo:.4f}, {hi:.4f}]  "
            f"pred={p[mask].mean():.4f}  actual={y[mask].mean():.4f}  n={mask.sum()}"
        )


def train_model():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM training_data", conn)
    conn.close()

    if len(df) < MIN_TRAINING_ROWS:
        print(f"Only {len(df)} rows found. Need at least {MIN_TRAINING_ROWS}.")
        return

    for col in FEATURE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            print(f"[WARN] feature '{col}' missing — NaN fill")
            df[col] = float("nan")

    y = pd.to_numeric(df["full_turnaround"], errors="coerce").fillna(0)
    if y.max() > 1.5:
        y = (y > 0).astype(int)
    else:
        y = y.round().astype(int)

    base_rate = float(y.mean()) if len(y) else 0.0
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    print(f"Rows: {len(df)}  positives: {n_pos} ({100 * base_rate:.2f}%)  negatives: {n_neg}")

    X = df[FEATURE_COLUMNS]

    if "sample_weight" in df.columns:
        weights = pd.to_numeric(df["sample_weight"], errors="coerce").fillna(1.0)
    else:
        weights = pd.Series(1.0, index=df.index)

    stratify_arg = y if y.nunique() >= 2 and y.value_counts().min() >= 2 else None
    if stratify_arg is None:
        print("[WARN] Cannot stratify split")

    X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
        X, y, weights, test_size=0.20, random_state=42, stratify=stratify_arg
    )

    strat2 = y_train if y_train.nunique() >= 2 and y_train.value_counts().min() >= 2 else None
    X_fit, X_cal, y_fit, y_cal, w_fit, w_cal = train_test_split(
        X_train, y_train, w_train, test_size=0.25, random_state=42, stratify=strat2
    )

    spw = max((len(y_fit) - float(y_fit.sum())) / max(float(y_fit.sum()), 1.0), 1.0)
    print(f"scale_pos_weight: {spw:.2f}")

    model = XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.03,
        subsample=0.9,
        colsample_bytree=0.9,
        scale_pos_weight=spw,
        random_state=42,
        eval_metric="logloss",
    )
    model.fit(X_fit, y_fit, sample_weight=w_fit)

    raw_cal = model.predict_proba(X_cal)[:, 1]
    calibrator = _fit_platt(raw_cal, y_cal)

    raw_test = model.predict_proba(X_test)[:, 1]
    cal_test = _apply_platt(calibrator, raw_test)

    print("\n--- Before calibration (test) ---")
    print(f"  mean pred: {raw_test.mean():.4f}  actual: {y_test.mean():.4f}")
    _reliability_table(y_test, raw_test)

    print("\n--- After Platt (test) ---")
    print(f"  mean pred: {cal_test.mean():.4f}  actual: {y_test.mean():.4f}")
    _reliability_table(y_test, cal_test)

    brier = brier_score_loss(y_test, cal_test)
    loss = log_loss(y_test, np.clip(cal_test, 1e-6, 1 - 1e-6))
    try:
        auc = roc_auc_score(y_test, cal_test)
    except ValueError:
        auc = float("nan")
        print("[WARN] ROC AUC undefined (one class in test)")

    importance = {
        feat: float(score)
        for feat, score in zip(FEATURE_COLUMNS, model.feature_importances_)
    }

    bundle = {
        "model": model,
        "calibrator": calibrator,
        "version": MODEL_VERSION,
        "base_rate": base_rate,
        "scale_pos_weight": float(spw),
        "feature_columns": list(FEATURE_COLUMNS),
        "feature_importance": importance,
    }
    joblib.dump(bundle, MODEL_FILE)

    run_id = save_model_run_with_importance(
        model_name="FTA_MODEL",
        version=MODEL_VERSION,
        training_rows=len(df),
        brier_score=float(brier),
        log_loss=float(loss),
        roc_auc=float(auc) if auc == auc else None,
        notes="scale_pos_weight + Platt calibration on logit(p)",
        feature_importance=importance,
    )

    print(f"\nModel bundle saved: {MODEL_FILE}")
    print(f"Version: {MODEL_VERSION}  run_id={run_id}")
    print(f"Base rate: {100 * base_rate:.2f}%")
    print(f"Brier: {brier:.4f}  LogLoss: {loss:.4f}  AUC: {auc:.4f}")
    print("\nFeature importance (saved to feature_importance)")
    for feature, score in sorted(importance.items(), key=lambda x: x[1], reverse=True):
        print(f"  {feature}: {score:.4f}")


if __name__ == "__main__":
    train_model()
