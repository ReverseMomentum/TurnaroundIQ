"""
Measure whether free Understat xG features help the FTA model.

Trains two identical XGB + Platt setups on the same split:
  A) full FEATURE_COLUMNS
  B) FEATURE_COLUMNS without avg_xg, avg_xga, xg_edge

    python -u models/xg_ablation.py

Does NOT overwrite fta_model.pkl — evaluation only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db
from tests.feature_config import FEATURE_COLUMNS

XG_FEATURES = ["avg_xg", "avg_xga", "xg_edge"]


def _logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _labels(s):
    y = pd.to_numeric(s, errors="coerce").fillna(0)
    if y.max() > 1.5:
        return (y > 0).astype(int)
    return y.round().astype(int)


def _fit_eval(X, y, w, label: str):
    strat = y if y.nunique() >= 2 and y.value_counts().min() >= 2 else None
    X_tr, X_te, y_tr, y_te, w_tr, _ = train_test_split(
        X, y, w, test_size=0.2, random_state=42, stratify=strat
    )
    strat2 = y_tr if y_tr.nunique() >= 2 and y_tr.value_counts().min() >= 2 else None
    X_fit, X_cal, y_fit, y_cal, w_fit, _ = train_test_split(
        X_tr, y_tr, w_tr, test_size=0.25, random_state=42, stratify=strat2
    )

    spw = max((len(y_fit) - float(y_fit.sum())) / max(float(y_fit.sum()), 1.0), 1.0)
    model = XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.9,
        scale_pos_weight=spw,
        random_state=42,
        eval_metric="logloss",
    )
    model.fit(X_fit, y_fit, sample_weight=w_fit)

    raw_cal = model.predict_proba(X_cal)[:, 1]
    cal = None
    if y_cal.sum() >= 5 and (len(y_cal) - y_cal.sum()) >= 5:
        cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        cal.fit(_logit(raw_cal).reshape(-1, 1), y_cal.astype(int))

    raw_te = model.predict_proba(X_te)[:, 1]
    if cal is not None:
        p = cal.predict_proba(_logit(raw_te).reshape(-1, 1))[:, 1]
    else:
        p = raw_te

    brier = brier_score_loss(y_te, p)
    loss = log_loss(y_te, np.clip(p, 1e-6, 1 - 1e-6))
    try:
        auc = roc_auc_score(y_te, p)
    except ValueError:
        auc = float("nan")

    # Importance among xG cols if present
    imp = {}
    if hasattr(model, "feature_importances_"):
        for feat, score in zip(X.columns, model.feature_importances_):
            if feat in XG_FEATURES:
                imp[feat] = float(score)

    print(f"\n=== {label} ===")
    print(f"  features: {X.shape[1]}  test n={len(y_te)}  base={100 * y_te.mean():.2f}%")
    print(f"  mean pred: {100 * p.mean():.2f}%")
    print(f"  Brier: {brier:.4f}  LogLoss: {loss:.4f}  AUC: {auc:.4f}")
    if imp:
        print("  xG importances:")
        for k, v in sorted(imp.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v:.4f}")
    else:
        print("  (no xG features in this model)")

    return {"brier": brier, "logloss": loss, "auc": auc, "imp": imp}


def main():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM training_data", conn)
    conn.close()

    if len(df) < 100:
        print(f"Need more training_data (have {len(df)})")
        return

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    y = _labels(df["full_turnaround"])
    w = (
        pd.to_numeric(df["sample_weight"], errors="coerce").fillna(1.0)
        if "sample_weight" in df.columns
        else pd.Series(1.0, index=df.index)
    )

    xg_non_null = df[XG_FEATURES].notna().any(axis=1).sum()
    print(f"Rows: {len(df)}  rows with any xG feature: {xg_non_null}")
    if xg_non_null < 50:
        print(
            "[WARN] Very few xG values populated — run collectors/understat_xg_trial.py "
            "then rebuild training_data before trusting this ablation."
        )

    cols_with = list(FEATURE_COLUMNS)
    cols_without = [c for c in FEATURE_COLUMNS if c not in XG_FEATURES]

    r_with = _fit_eval(df[cols_with], y, w, "WITH xG (avg_xg, avg_xga, xg_edge)")
    r_without = _fit_eval(df[cols_without], y, w, "WITHOUT xG features")

    print("\n" + "=" * 50)
    print("ABLATION SUMMARY")
    print("=" * 50)
    db = r_with["brier"] - r_without["brier"]
    da = (r_with["auc"] or 0) - (r_without["auc"] or 0)
    print(f"Brier  with - without: {db:+.4f}  (negative = xG helps)")
    print(f"AUC    with - without: {da:+.4f}  (positive = xG helps)")
    if db < -0.002 or da > 0.01:
        print("Verdict: xG features show a meaningful lift — keep them.")
    elif abs(db) < 0.001 and abs(da) < 0.005:
        print("Verdict: neutral — free xG not hurting; low priority to pay for more.")
    else:
        print("Verdict: weak / mixed — revisit after more seasons of coverage.")


if __name__ == "__main__":
    main()
