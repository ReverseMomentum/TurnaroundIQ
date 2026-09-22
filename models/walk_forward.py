"""
Chronological / walk-forward validation for the FTA model.

Unlike random holdout, each fold trains only on matches *before* the
test window, then scores the next window — closer to live deployment.

    python -u models/walk_forward.py
    python -u models/walk_forward.py --folds 5 --min-train 800

Dates are resolved from historical_matches.date or match_results.processed_at
via training_data.match_id (training_data itself has no match_date column).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db
from tests.feature_config import FEATURE_COLUMNS


def _logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _labels(series: pd.Series) -> np.ndarray:
    y = pd.to_numeric(series, errors="coerce").fillna(0)
    if y.max() > 1.5:
        return (y > 0).astype(int).to_numpy()
    return y.round().astype(int).to_numpy()


def _fit_platt(raw_probs, y):
    y = np.asarray(y).astype(int)
    if y.sum() < 5 or (len(y) - y.sum()) < 5:
        return None
    x = _logit(np.asarray(raw_probs, dtype=float)).reshape(-1, 1)
    cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    cal.fit(x, y)
    return cal


def _apply_platt(calibrator, raw_probs):
    raw = np.asarray(raw_probs, dtype=float)
    if calibrator is None:
        return raw
    x = _logit(raw).reshape(-1, 1)
    return calibrator.predict_proba(x)[:, 1]


def _load_dated_training() -> pd.DataFrame:
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM training_data", conn)
    if df.empty:
        conn.close()
        return df

    # Best-effort match date from historical or live results
    try:
        hist = pd.read_sql_query(
            "SELECT match_id, date AS match_date FROM historical_matches",
            conn,
        )
    except Exception:
        hist = pd.DataFrame(columns=["match_id", "match_date"])
    try:
        live = pd.read_sql_query(
            "SELECT match_id, processed_at AS match_date FROM match_results",
            conn,
        )
    except Exception:
        live = pd.DataFrame(columns=["match_id", "match_date"])
    conn.close()

    dates = {}
    for _, row in hist.iterrows():
        if row.get("match_id") is not None and row.get("match_date"):
            dates[str(row["match_id"])] = str(row["match_date"])[:10]
    for _, row in live.iterrows():
        mid = str(row.get("match_id") or "")
        if mid and mid not in dates and row.get("match_date"):
            dates[mid] = str(row["match_date"])[:10]

    df["match_id"] = df["match_id"].astype(str)
    df["match_date"] = df["match_id"].map(dates)

    # Fallback: rows with no joinable date keep NaT and sort last among undated
    parsed = pd.to_datetime(df["match_date"], errors="coerce", utc=True)
    # If still mostly empty, invent order from sample_weight (higher = more recent)
    if parsed.notna().sum() < max(50, int(0.2 * len(df))):
        print(
            "[WARN] Few match dates resolved — ordering by sample_weight "
            "(higher weight ≈ more recent) as fallback"
        )
        w = pd.to_numeric(df.get("sample_weight"), errors="coerce").fillna(0.5)
        # synthetic increasing dates by weight rank
        rank = w.rank(method="first")
        base = pd.Timestamp("2015-01-01", tz="UTC")
        parsed = base + pd.to_timedelta(rank.astype(int), unit="D")

    df["_ts"] = parsed
    df = df.dropna(subset=["_ts"]).sort_values("_ts").reset_index(drop=True)
    return df


def _prepare_xyw(df: pd.DataFrame):
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    y = _labels(df["full_turnaround"])
    X = df[FEATURE_COLUMNS]
    if "sample_weight" in df.columns:
        w = pd.to_numeric(df["sample_weight"], errors="coerce").fillna(1.0).to_numpy()
    else:
        w = np.ones(len(df))
    return X, y, w


def _train_fold(X_train, y_train, w_train):
    n_pos = float(y_train.sum())
    n_neg = float(len(y_train) - n_pos)
    spw = max(n_neg / max(n_pos, 1.0), 1.0)

    # Hold out last 20% of *train* chronologically for Platt
    cut = max(int(len(X_train) * 0.8), 1)
    if cut >= len(X_train) - 5:
        cut = max(len(X_train) - 10, 1)

    X_fit, X_cal = X_train.iloc[:cut], X_train.iloc[cut:]
    y_fit, y_cal = y_train[:cut], y_train[cut:]
    w_fit = w_train[:cut]

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

    raw_cal = model.predict_proba(X_cal)[:, 1] if len(X_cal) else np.array([])
    calibrator = _fit_platt(raw_cal, y_cal) if len(y_cal) else None
    return model, calibrator, spw


def _bucket_line(y, p, lo, hi, last=False):
    p_pct = p * 100.0
    mask = (p_pct >= lo) & (p_pct <= hi if last else p_pct < hi)
    n = int(mask.sum())
    if n == 0:
        return None
    pred = float(p_pct[mask].mean())
    act = float(y[mask].mean() * 100.0)
    return f"  {lo:5.1f}-{hi:5.1f} | {n:5d} | {pred:10.2f} | {act:8.2f} | {act - pred:+.2f}"


def run_walk_forward(folds: int = 5, min_train: int = 500):
    df = _load_dated_training()
    if len(df) < min_train + 50:
        print(f"Need more dated rows (have {len(df)}, min_train={min_train})")
        return

    X_all, y_all, w_all = _prepare_xyw(df)
    n = len(df)
    print(f"Dated training rows: {n}")
    print(f"Date range: {df['_ts'].iloc[0].date()} → {df['_ts'].iloc[-1].date()}")
    print(f"Overall FTA base rate: {100 * y_all.mean():.2f}%")
    print(f"Walk-forward folds: {folds}  min_train: {min_train}\n")

    # Expanding window: fold k tests quantile band (k/folds, (k+1)/folds)
    # but only after min_train rows of history.
    results = []
    edges = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 100.0]

    for k in range(folds):
        # Test window is the (k+1)-th equal slice of the *post min_train* tail
        usable = n - min_train
        if usable < folds * 20:
            print("[WARN] Not enough tail rows for requested folds — reducing")
            folds = max(usable // 30, 2)
            if k >= folds:
                break
            usable = n - min_train

        test_start = min_train + int(usable * k / folds)
        test_end = min_train + int(usable * (k + 1) / folds)
        if test_end <= test_start:
            continue

        train_idx = np.arange(0, test_start)
        test_idx = np.arange(test_start, test_end)
        if len(train_idx) < min_train or len(test_idx) < 20:
            continue

        X_tr, y_tr, w_tr = X_all.iloc[train_idx], y_all[train_idx], w_all[train_idx]
        X_te, y_te = X_all.iloc[test_idx], y_all[test_idx]

        if y_tr.sum() < 5 or y_te.sum() < 1:
            print(f"Fold {k + 1}: skipped (too few positives)")
            continue

        model, calibrator, spw = _train_fold(X_tr, y_tr, w_tr)
        raw = model.predict_proba(X_te)[:, 1]
        p = _apply_platt(calibrator, raw)

        brier = brier_score_loss(y_te, p)
        try:
            loss = log_loss(y_te, np.clip(p, 1e-6, 1 - 1e-6))
        except Exception:
            loss = float("nan")
        try:
            auc = roc_auc_score(y_te, p)
        except ValueError:
            auc = float("nan")

        t0 = df["_ts"].iloc[test_idx[0]].date()
        t1 = df["_ts"].iloc[test_idx[-1]].date()
        print("=" * 60)
        print(
            f"Fold {k + 1}/{folds}  train n={len(train_idx)}  "
            f"test n={len(test_idx)}  window {t0} → {t1}"
        )
        print(f"  train base={100 * y_tr.mean():.2f}%  test base={100 * y_te.mean():.2f}%")
        print(f"  mean pred={100 * p.mean():.2f}%  scale_pos_weight={spw:.2f}")
        print(f"  Brier={brier:.4f}  LogLoss={loss:.4f}  AUC={auc:.4f}")
        print("  Bucket | n | mean pred % | actual % | gap")
        for i in range(len(edges) - 1):
            line = _bucket_line(
                y_te, p, edges[i], edges[i + 1], last=(i == len(edges) - 2)
            )
            if line:
                print(line)

        results.append(
            {
                "fold": k + 1,
                "train_n": len(train_idx),
                "test_n": len(test_idx),
                "test_start": str(t0),
                "test_end": str(t1),
                "base_rate": float(y_te.mean()),
                "mean_pred": float(p.mean()),
                "brier": float(brier),
                "logloss": float(loss) if loss == loss else None,
                "auc": float(auc) if auc == auc else None,
            }
        )

    if not results:
        print("No folds completed")
        return

    print("\n" + "=" * 60)
    print("WALK-FORWARD SUMMARY")
    print("=" * 60)
    briers = [r["brier"] for r in results]
    aucs = [r["auc"] for r in results if r["auc"] is not None]
    print(f"Folds completed: {len(results)}")
    print(f"Mean Brier: {np.mean(briers):.4f}  (±{np.std(briers):.4f})")
    if aucs:
        print(f"Mean AUC:   {np.mean(aucs):.4f}  (±{np.std(aucs):.4f})")
    print("\nPer-fold:")
    for r in results:
        auc_s = f"{r['auc']:.3f}" if r["auc"] is not None else "n/a"
        print(
            f"  fold {r['fold']}: {r['test_start']}→{r['test_end']}  "
            f"n={r['test_n']}  base={100 * r['base_rate']:.1f}%  "
            f"pred={100 * r['mean_pred']:.1f}%  "
            f"Brier={r['brier']:.4f}  AUC={auc_s}"
        )
    print("\nHow to read:")
    print("  Stable Brier/AUC across folds → model generalises over time")
    print("  Rising Brier on later folds → concept drift / stale features")
    print("  mean pred ≈ base rate → calibration holding out-of-time")


def main():
    parser = argparse.ArgumentParser(description="Walk-forward FTA validation")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument(
        "--min-train",
        type=int,
        default=500,
        help="Minimum chronological training rows before first test window",
    )
    args = parser.parse_args()
    run_walk_forward(folds=args.folds, min_train=args.min_train)


if __name__ == "__main__":
    main()
