"""
Show feature importance across recent model runs.

    python -u models/feature_importance_report.py
    python -u models/feature_importance_report.py --top 15 --runs 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_db, get_feature_importance_history, get_model_runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=15, help="Top N features to show")
    parser.add_argument("--runs", type=int, default=5, help="How many recent runs")
    args = parser.parse_args()

    runs = get_model_runs()[: args.runs]
    if not runs:
        print("No model_runs yet — train once first: python -u run.py train")
        return

    # model_runs columns from SELECT *: id, model_name, version, trained_at,
    # training_rows, brier_score, log_loss, roc_auc, notes
    print("Recent model runs")
    print("-" * 72)
    for r in runs:
        rid = r[0]
        print(
            f"  id={rid}  {r[2]}  {r[3]}  rows={r[4]}  "
            f"Brier={r[5]}  AUC={r[7]}"
        )

    # Pivot: feature -> list of scores newest-first
    hist = get_feature_importance_history(limit_runs=args.runs)
    if not hist:
        print("\nNo feature_importance rows yet (retrain after this update).")
        return

    by_feat: dict[str, list[tuple]] = {}
    for run_id, trained_at, version, feature, importance, rank in hist:
        by_feat.setdefault(feature, []).append(
            (run_id, trained_at, version, importance, rank)
        )

    # Rank features by importance on the newest run
    newest_run_id = runs[0][0]
    newest_scores = []
    for feat, entries in by_feat.items():
        for run_id, trained_at, version, imp, rank in entries:
            if run_id == newest_run_id:
                newest_scores.append((feat, imp, rank))
                break
    newest_scores.sort(key=lambda x: x[1], reverse=True)

    print(f"\nTop {args.top} features (latest run id={newest_run_id})")
    print("-" * 72)
    print(f"{'feature':32} {'imp':>8}  history (newest → older)")
    for feat, imp, rank in newest_scores[: args.top]:
        series = by_feat.get(feat, [])
        # already roughly newest first if query ordered DESC
        hist_str = " → ".join(f"{e[3]:.3f}" for e in series[: args.runs])
        print(f"{rank:2d}. {feat:28} {imp:8.4f}  {hist_str}")

    print("\nTip: rising/falling scores across runs signal drift or data shifts.")


if __name__ == "__main__":
    main()
