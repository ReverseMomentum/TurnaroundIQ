"""
Live turnaround model: once a team has been 2 goals up, what is the chance it
still fails to win from HERE (this minute, this score)?

It powers the cash-out calculator's "let it ride or trade out" view. Trained on
the same goal timelines as the FTA model:

  every team-side that went 2 up -> a "state" at the moment it went 2 up, then
  every 5 minutes and after every later goal: (minute, current score) + the
  team's pre-match profile (point-in-time, nothing from the match itself)
  label: the team did NOT win in the end

    python -u models/live_turnaround.py train    # time-split check, then fit + save
    python -u models/live_turnaround.py check    # the time-split check only

The check fits on the earlier 85% of matches and scores the latest 15%,
against a plain "score difference x minute" table built from the same
training games: the model is only worth showing if it beats that table.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import fta_path_model as pm  # noqa: E402

MODEL_FILE = PROJECT_ROOT / "live_turnaround.pkl"
VERSION = "LIVE-1"
STEP = 5            # minutes between sampled states
LAST_MINUTE = 85    # states after this say little (and stoppage minutes are fuzzy)
HOLDOUT = 0.15
# Turnarounds have become more common (longer added time), so recent seasons can
# count more. check() keeps the weighting only if it scores the latest games better.
RECENCY_OPTIONS = [None, 1460.0, 730.0]   # half-life in days; None = every season equal

PRE = ["is_home", "t_fail_rate", "o_rescue_rate", "lg_fail_rate", "lg_goals",
       "t_gf", "t_ga", "o_gf", "o_ga", "t_lead_keep", "o_lead_keep"]
PRE_X_TIME = ["t_fail_rate", "o_rescue_rate", "lg_fail_rate", "lg_goals"]
DIFF_BUCKETS = ("d_level_or_behind", "d_1", "d_2", "d_3", "d_4plus")

_bundle_cache = {"bundle": None, "mtime": None}


def _diff_bucket(d):
    return 0 if d <= 0 else min(d, 4)


def state_features(pre, minute, team_goals, opp_goals):
    """Features for one in-play state. pre = pre-match features (fta_path_model)."""
    m = max(0.0, min(float(minute), 90.0))
    rem = (90.0 - m) / 90.0
    b = _diff_bucket(team_goals - opp_goals)
    f = {"rem": rem, "rem2": rem * rem, "goals_so_far": float(team_goals + opp_goals)}
    for i, name in enumerate(DIFF_BUCKETS):
        on = 1.0 if i == b else 0.0
        f[name] = on
        f[name + "_rem"] = on * rem
    for k in PRE:
        f[k] = float(pre.get(k, 0.0) or 0.0)
    for k in PRE_X_TIME:
        f[k + "_rem"] = f[k] * rem
    return f


FEATURES = (["rem", "rem2", "goals_so_far"]
            + [n for name in DIFF_BUCKETS for n in (name, name + "_rem")]
            + PRE + [k + "_rem" for k in PRE_X_TIME])


def side_states(goals, side):
    """[(minute, team_goals, opp_goals)] for one side from the moment it first led by 2.
    goals: [(minute, side)] chronological. Empty if it never went 2 up."""
    tg = og = 0
    start = None
    events = []
    for minute, s in goals:
        minute = int(minute or 0)
        if s == side:
            tg += 1
        elif s in (1, 2):
            og += 1
        events.append((minute, tg, og))
        if start is None and tg - og >= 2:
            start = len(events) - 1
    if start is None:
        return []
    m2, tg2, og2 = events[start]
    states = {(m2, tg2, og2)}
    later = events[start + 1:]
    for minute, a, b in later:              # right after every later goal
        if minute <= LAST_MINUTE:
            states.add((minute, a, b))
    t = (m2 // STEP + 1) * STEP             # and every STEP minutes
    while t <= LAST_MINUTE:
        a, b = tg2, og2
        for minute, x, y in later:
            if minute <= t:
                a, b = x, y
        states.add((t, a, b))
        t += STEP
    return sorted(states)


def build_states(matches=None, rows=None):
    """(X, y, days, first) for every in-play state; first marks each side's 2-up moment."""
    if matches is None:
        matches = pm.load_matches()
    if rows is None:
        rows, _, _ = pm.replay(matches)
    X, y, days, first = [], [], [], []
    for i, m in enumerate(matches):
        goals = m.get("goals")
        if goals is None:
            continue
        for side in (1, 2):
            pre = rows[2 * i + side - 1]
            won = (m["fh"] > m["fa"]) if side == 1 else (m["fa"] > m["fh"])
            for j, (minute, a, b) in enumerate(side_states(goals, side)):
                f = state_features(pre, minute, a, b)
                X.append([f[k] for k in FEATURES])
                y.append(0 if won else 1)
                days.append(m["day"])
                first.append(j == 0)
    return (np.array(X, dtype=float), np.array(y, dtype=int),
            np.array(days), np.array(first, dtype=bool))


def _fit(X, y, days=None, half_life=None):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=3000))
    if half_life and days is not None:
        w = pm.recency_weights(days, half_life)
        model.fit(X, y, logisticregression__sample_weight=w)
    else:
        model.fit(X, y)
    return model


def _table_key(row):
    rem_i = FEATURES.index("rem")
    idx = [FEATURES.index(n) for n in DIFF_BUCKETS]
    return f"{int(np.argmax(row[idx]))},{int((1 - row[rem_i]) * 9)}"


def _table_counts(X, y):
    """No-win counts by (score-difference bucket, 10-minute bin)."""
    cells = defaultdict(lambda: [0, 0])
    for row, lab in zip(X, y):
        c = cells[_table_key(row)]
        c[0] += int(lab)
        c[1] += 1
    return {"cells": dict(cells), "overall": float(np.mean(y))}


def _table_rate(table, key):
    k, n = table["cells"].get(key, (0, 0))
    return (k + 5 * table["overall"]) / (n + 5)   # light shrink for thin cells


def _table_baseline(X, y):
    table = _table_counts(X, y)
    return lambda Xt: np.array([_table_rate(table, _table_key(r)) for r in Xt])


def _bands(y, p, title):
    edges = [0, 0.02, 0.05, 0.10, 0.20, 0.35, 1.01]
    print(title)
    print("  predicted   |      n  | predicted | actual")
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi)
        if mask.sum():
            print(f"  {100*lo:>4.0f}-{100*min(hi,1):<4.0f}%  | {mask.sum():>7} | {100*p[mask].mean():>8.1f}% | "
                  f"{100*y[mask].mean():>5.1f}%")


def _safe_auc(y, p):
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y, p)) if len(y) > 50 else None
    except ValueError:
        return None


def check(data=None, verbose=True):
    from sklearn.metrics import log_loss, roc_auc_score
    X, y, days, first = data if data is not None else build_states()
    if len(y) < 2000:
        raise SystemExit(f"only {len(y)} in-play states - need goal timelines (run the historical pipeline)")
    cut = np.quantile(days, 1 - HOLDOUT)
    tr, te = days < cut, days >= cut
    tried = {}
    best_hl, p = None, None
    for hl in RECENCY_OPTIONS:
        ph = _fit(X[tr], y[tr], days[tr], hl).predict_proba(X[te])[:, 1]
        tried[hl] = float(log_loss(y[te], np.clip(ph, 1e-6, 1 - 1e-6), labels=[0, 1]))
        if p is None or tried[hl] < tried[best_hl] - 1e-5:
            best_hl, p = hl, ph
    base = _table_baseline(X[tr], y[tr])(X[te])
    flat = np.full_like(p, y[tr].mean())
    out = {
        "states_train": int(tr.sum()), "states_test": int(te.sum()),
        "log_loss": float(log_loss(y[te], np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "log_loss_table": float(log_loss(y[te], np.clip(base, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "log_loss_flat": float(log_loss(y[te], flat, labels=[0, 1])),
        "auc": float(roc_auc_score(y[te], p)),
        "auc_table": float(roc_auc_score(y[te], base)),
        "first_auc": _safe_auc(y[te & first], p[first[te]]),
        "actual": float(y[te].mean()), "pred": float(p.mean()),
    }
    out["beats_table"] = out["log_loss"] < out["log_loss_table"]
    out["half_life_days"] = best_hl
    out["recency_tried"] = {("equal" if k is None else f"{k / 365:.0f}y"): v for k, v in tried.items()}
    if verbose:
        print(f"in-play states: {len(y)} from {int(first.sum())} team-sides that went 2 up "
              f"(train {out['states_train']}, latest {int(100*HOLDOUT)}% test {out['states_test']})")
        print(f"  held-out log loss  model {out['log_loss']:.4f}  | score x minute table "
              f"{out['log_loss_table']:.4f}  | flat rate {out['log_loss_flat']:.4f}")
        print(f"  held-out AUC       model {out['auc']:.3f}  | table {out['auc_table']:.3f}"
              + (f"  | at the 2-up moment {out['first_auc']:.3f}" if out["first_auc"] else ""))
        print(f"  no-win rate        predicted {100*out['pred']:.1f}%  actual {100*out['actual']:.1f}%")
        _bands(y[te], p, "Held-out calibration (all states):")
        _bands(y[te & first], p[first[te]], "Held-out calibration (at the moment of going 2 up):")
        print("  recency weighting (held-out log loss): "
              + ", ".join(f"{k} {v:.4f}" for k, v in out["recency_tried"].items())
              + f"  -> using {'equal' if best_hl is None else f'half-life {best_hl / 365:.0f}y'}")
        print(f"  -> model {'BEATS' if out['beats_table'] else 'does NOT beat'} the plain score x minute table")
    return out


def train(save=True):
    data = build_states()
    report = check(data)
    X, y, days, _ = data
    model = _fit(X, y, days, report["half_life_days"])
    bundle = {"version": VERSION, "features": FEATURES, "model": model, "check": report,
              "trained_at": datetime.now(timezone.utc).isoformat(), "states": int(len(y)),
              # only show model numbers in the app when they beat the simple table
              "use_model": bool(report["beats_table"])}
    if not bundle["use_model"]:
        bundle["table"] = _table_counts(X, y)
    if save:
        joblib.dump(bundle, MODEL_FILE)
        _bundle_cache.update(bundle=None, mtime=None)
        print(f"saved {MODEL_FILE.name} ({VERSION}, {'model' if bundle['use_model'] else 'table fallback'})")
    return bundle


def load_bundle():
    if not MODEL_FILE.is_file():
        return None
    mtime = MODEL_FILE.stat().st_mtime
    if _bundle_cache["bundle"] is None or _bundle_cache["mtime"] != mtime:
        _bundle_cache.update(bundle=joblib.load(MODEL_FILE), mtime=mtime)
    return _bundle_cache["bundle"]


def predict_live(team, opponent, league, is_home, minute, team_goals, opp_goals):
    """P(team fails to win from this state), in percent; None without a trained bundle."""
    bundle = load_bundle()
    if bundle is None:
        return None
    pre, t, o = pm.prematch_features(team, opponent, league, is_home)
    f = state_features(pre, minute, team_goals, opp_goals)
    if bundle.get("use_model", True):
        x = np.array([[f[k] for k in bundle["features"]]], dtype=float)
        p = float(bundle["model"].predict_proba(x)[0, 1])
        how = "model"
    else:
        x = np.array([f[k] for k in FEATURES], dtype=float)
        p = _table_rate(bundle["table"], _table_key(x))
        how = "score x minute table"
    return {
        "no_win_pct": round(100 * p, 1),
        "win_pct": round(100 * (1 - p), 1),
        "method": how,
        "data_confidence": pm.data_confidence(t, o),
        "model_version": bundle["version"],
        "trained_at": bundle.get("trained_at"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["train", "check"])
    args = ap.parse_args(argv)
    if args.command == "train":
        train()
    else:
        check()


if __name__ == "__main__":
    main()
