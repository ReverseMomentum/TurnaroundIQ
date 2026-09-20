"""
Backtest calibrated fta_pct vs realised full_turnaround.

    python -u models/backtest_calibration.py
    python -u models/backtest_calibration.py --holdout 0.25

Prints reliability buckets: mean predicted % vs actual hit rate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db
from models.model import load_bundle, _calibrate_prob, _logit
from tests.feature_config import FEATURE_COLUMNS


def _labels(series: pd.Series) -> np.ndarray:
    y = pd.to_numeric(series, errors="coerce").fillna(0)
    if y.max() > 1.5:
        return (y > 0).astype(int).to_numpy()
    return y.round().astype(int).to_numpy()


def _predict_probs(model, calibrator, X: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(X)[:, 1]
    if calibrator is None:
        return raw.astype(float)
    out = np.empty(len(raw), dtype=float)
    for i, p in enumerate(raw):
        out[i] = _calibrate_prob(float(p), calibrator)
    return out


def _bucket_report(y: np.ndarray, p: np.ndarray, edges_pct: list[float]) -> None:
    """edges_pct in percent units, e.g. [0, 1, 2, 3, 5, 8, 100]."""
    y = y.astype(float)
    p_pct = p * 100.0
    print("\nBucket | n | mean pred % | actual % | gap")
    print("-" * 52)
    for i in range(len(edges_pct) - 1):
        lo, hi = edges_pct[i], edges_pct[i + 1]
        if i < len(edges_pct) - 2:
            mask = (p_pct >= lo) & (p_pct < hi)
        else:
            mask = (p_pct >= lo) & (p_pct <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        pred = float(p_pct[mask].mean())
        act = float(y[mask].mean() * 100.0)
        print(f"{lo:5.1f}-{hi:5.1f} | {n:5d} | {pred:10.2f} | {act:8.2f} | {act - pred:+.2f}")


def main():
    parser = argparse.ArgumentParser(description="FTA calibration backtest")
    parser.add_argument(
        "--holdout",
        type=float,
        default=0.25,
        help="Fraction of rows held out for scoring (default 0.25). Use 0 for full-sample (optimistic).",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    bundle = load_bundle()
    model = bundle["model"]
    calibrator = bundle.get("calibrator")
    version = bundle.get("version") or "unknown"
    base_rate = bundle.get("base_rate")

    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM training_data", conn)
    conn.close()

    if df.empty:
        print("No training_data rows")
        return

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    y_all = _labels(df["full_turnaround"])
    X_all = df[FEATURE_COLUMNS]

    if args.holdout and 0 < args.holdout < 1:
        strat = y_all if len(np.unique(y_all)) > 1 and np.min(np.bincount(y_all)) >= 2 else None
        _, X, _, y = train_test_split(
            X_all, y_all, test_size=args.holdout, random_state=args.seed, stratify=strat
        )
        split_note = f"holdout {args.holdout:.0%} ({len(y)} rows)"
    else:
        X, y = X_all, y_all
        split_note = f"full sample ({len(y)} rows) — optimistic"

    p = _predict_probs(model, calibrator, X)

    print(f"Model: {version}")
    if base_rate is not None:
        print(f"Train base rate (from bundle): {100 * float(base_rate):.2f}%")
    print(f"Eval: {split_note}")
    print(f"Eval base rate: {100 * y.mean():.2f}%")
    print(f"Mean predicted: {100 * p.mean():.2f}%")
    print(f"Pred min/max: {100 * p.min():.2f}% / {100 * p.max():.2f}%")

    try:
        brier = brier_score_loss(y, p)
        loss = log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))
        auc = roc_auc_score(y, p)
        print(f"Brier: {brier:.4f}  LogLoss: {loss:.4f}  AUC: {auc:.4f}")
    except Exception as exc:
        print(f"Metrics skipped: {exc}")

    edges = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 100.0]
    _bucket_report(y, p, edges)

    print("\nHow to read:")
    print("  actual ≈ pred  → well calibrated in that band")
    print("  actual > pred  → model under-calls FTA")
    print("  actual < pred  → model over-calls FTA")
    print("  empty high buckets → model never outputs those probs on this set")


if __name__ == "__main__":
    main()
