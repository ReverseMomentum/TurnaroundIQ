#!/usr/bin/env python3
"""
The Stables: morning prices vs the off. You bet in the morning, not at the off, so the
question is how good the MORNING price is, and whether the horse's own record adds
anything on top of it. Uses Betfair's daily BSP files (data/bsp/), which carry each
runner's morning average traded price (MORNINGWAP), its SP and the result, and
rac_history for each horse's earlier runs (no jockeys or trainers in those files).

  1. Accuracy: morning price vs SP against results (win log loss, place Brier)
  2. A ranking model on top of the MORNING price, trained on the earlier races:
        strength = a * log(morning chance) + horse-record features
     scored on the held-back months against the morning price alone and SP
  3. Price moves: do the features predict which horses shorten from morning to SP?
  4. Paper win bets at the morning price where model chance x price is 5%+ over 1:
     return, and how often the price beat SP (CLV)

    scripts/cron_job.sh morning python -u scripts/stables_morning_test.py
    scripts/cron_job.sh morning python -u scripts/stables_morning_test.py --since 2024-01-01 --test-months 6

Writes logs/stables_morning_test.json. Nothing is changed in the app.
"""
import argparse
import bisect
import json
import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from database import get_db  # noqa: E402
from racing import bsp_files, store  # noqa: E402
from racing.backtest import _f, _rows  # noqa: E402
from racing.live_features import distance_from_name, horse_key  # noqa: E402

FEATURES = ["log_runs", "first_run", "log_days", "days_missing", "last_placed", "last_won",
            "place_excess", "win_excess", "course_rate", "distance_rate"]
PRIOR_PLACE, SHRINK = 0.30, 4.0
COMMISSION = 0.02
EDGE = 0.05


def load_races(start: date, end: date) -> list[dict]:
    races, day = [], start
    while day <= end:
        for region in ("uk", "ire"):
            win = bsp_files.fetch(region, "win", day)
            if not win:
                continue
            place = bsp_files.fetch(region, "place", day) or ""
            pl = defaultdict(dict)
            for r in _rows(place):
                pl[(r.get("MENU_HINT"), r.get("EVENT_DT"))][r.get("SELECTION_ID")] = r.get("WIN_LOSE")
            by = defaultdict(list)
            for r in _rows(win):
                by[(r.get("MENU_HINT"), r.get("EVENT_DT"))].append(r)
            for key, rs in by.items():
                d = bsp_files._date(key[1])
                if not d or len(rs) < 4:
                    continue
                mw = [_f(r.get("MORNINGWAP")) for r in rs]
                sp = [_f(r.get("BSP")) for r in rs]
                if not all(mw) or not all(sp):
                    continue
                won = [1 if r.get("WIN_LOSE") == "1" else 0 for r in rs]
                if sum(won) != 1:
                    continue
                p_pl = pl.get(key) or {}
                placed = [1 if p_pl.get(r.get("SELECTION_ID")) == "1" else 0 for r in rs] if p_pl else None
                k = sum(placed) if placed else 0
                races.append({
                    "date": d, "course": bsp_files.course_from_menu(key[0]),
                    "dist": distance_from_name(rs[0].get("EVENT_NAME")),
                    "horses": [horse_key(r.get("SELECTION_NAME")) for r in rs],
                    "morning": np.array(mw, float), "sp": np.array(sp, float), "won": np.array(won),
                    "placed": np.array(placed) if placed and 1 <= k < len(rs) else None, "k": k,
                    "vol": sum(_f(r.get("MORNINGTRADEDVOL")) or 0 for r in rs)})
        day += timedelta(days=1)
        if day.day == 1:
            print(f"  {day:%Y-%m}: {len(races)} races", flush=True)
    return races


def load_history() -> dict:
    conn = get_db()
    store.ensure_tables(conn)
    hist = defaultdict(list)
    for h, d, course, dist, placed, pos, ew, ep in conn.execute(
            "SELECT horse_key, date, course, dist_f, placed, pos, exp_win, exp_place FROM rac_history"):
        hist[h].append((str(d)[:10], (course or "").lower(), dist, placed, 1 if pos == 1 else 0, ew, ep))
    conn.close()
    for h in hist:
        hist[h].sort(key=lambda r: r[0])      # by date only (other fields can be empty)
    return hist


def features(race: dict, hist: dict) -> np.ndarray:
    out = []
    for h in race["horses"]:
        rows = hist.get(h, [])
        rows = rows[:bisect.bisect_left(rows, (race["date"],))]       # strictly earlier days
        n = len(rows)
        f = dict.fromkeys(FEATURES, 0.0)
        f["log_runs"] = math.log1p(n)
        f["first_run"] = 1.0 if n == 0 else 0.0
        if n:
            try:
                days = (date.fromisoformat(race["date"]) - date.fromisoformat(rows[-1][0])).days
                f["log_days"] = math.log1p(max(0, days))
            except ValueError:
                f["days_missing"] = 1.0
            last = rows[-1]
            f["last_placed"] = float(last[3] or 0)
            f["last_won"] = float(last[4])
            pe = [r[3] - r[6] for r in rows if r[3] is not None and r[6] is not None]
            we = [r[4] - r[5] for r in rows if r[5] is not None]
            f["place_excess"] = sum(pe) / (len(pe) + SHRINK)
            f["win_excess"] = sum(we) / (len(we) + SHRINK)
            cr = [r[3] for r in rows if r[3] is not None and race["course"] and r[1].startswith(race["course"][:4])]
            f["course_rate"] = (sum(cr) + PRIOR_PLACE * SHRINK) / (len(cr) + SHRINK) - PRIOR_PLACE
            dr = [r[3] for r in rows if r[3] is not None and race["dist"] and r[2] is not None
                  and abs(r[2] - race["dist"]) <= 1]
            f["distance_rate"] = (sum(dr) + PRIOR_PLACE * SHRINK) / (len(dr) + SHRINK) - PRIOR_PLACE
        else:
            f["days_missing"] = 1.0
        out.append([f[k] for k in FEATURES])
    return np.array(out, float)


def chances(prices: np.ndarray) -> np.ndarray:
    q = 1 / prices
    return q / q.sum()


def pad(races, key="X"):
    N = max(len(r["horses"]) for r in races)
    F = races[0][key].shape[1]
    R = len(races)
    logp, X, mask, y = np.zeros((R, N)), np.zeros((R, N, F)), np.zeros((R, N), bool), np.zeros(R, int)
    for i, r in enumerate(races):
        n = len(r["horses"])
        logp[i, :n] = np.log(chances(r["morning"]))
        X[i, :n] = r[key]
        mask[i, :n] = True
        y[i] = int(np.argmax(r["won"]))
    return logp, X, mask, y


def nll(theta, logp, X, mask, y, l2=1e-3):
    a, b = theta[0], theta[1:]
    u = a * logp + X @ b
    u = np.where(mask, u, -1e9)
    m = u.max(axis=1, keepdims=True)
    e = np.exp(u - m) * mask
    s = e.sum(axis=1, keepdims=True)
    p = e / s
    R = len(y)
    loss = -(u[np.arange(R), y] - m[:, 0] - np.log(s[:, 0])).mean() + l2 * (b @ b)
    g_u = p.copy()
    g_u[np.arange(R), y] -= 1
    g_u /= R
    ga = (g_u * logp).sum()
    gb = np.einsum("rn,rnf->f", g_u, X) + 2 * l2 * b
    return loss, np.concatenate([[ga], gb])


def model_p(theta, race) -> np.ndarray:
    u = theta[0] * np.log(chances(race["morning"])) + race["X"] @ theta[1:]
    e = np.exp(u - u.max())
    return e / e.sum()


def harville_topk(p: np.ndarray, k: int, sims: int = 400, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    g = -np.log(-np.log(rng.random((sims, len(p)))))
    order = np.argsort(-(np.log(p)[None, :] + g), axis=1)[:, :k]
    return np.bincount(order.ravel(), minlength=len(p)) / sims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--until", type=date.fromisoformat, default=date.today() - timedelta(days=2))
    ap.add_argument("--test-months", type=int, default=6)
    a = ap.parse_args()
    print(f"loading BSP files {a.since} to {a.until}", flush=True)
    races = load_races(a.since, a.until)
    if len(races) < 3000:
        print(f"only {len(races)} races with morning prices: not enough. Failures: {bsp_files.failures[:3]}")
        sys.exit(1)
    print(f"{len(races)} races with a morning price for every runner; loading horse histories", flush=True)
    hist = load_history()
    for r in races:
        r["X"] = features(r, hist)
    cut = (a.until - timedelta(days=30 * a.test_months)).isoformat()
    train = [r for r in races if r["date"] < cut]
    test = [r for r in races if r["date"] >= cut]
    allX = np.vstack([r["X"] for r in train])
    mu, sd = allX.mean(0), allX.std(0) + 1e-9
    for r in races:
        r["X"] = (r["X"] - mu) / sd
    print(f"training on {len(train)} races before {cut}, testing on {len(test)}", flush=True)

    # 1. accuracy of morning vs SP
    def win_ll(rs, f):
        return float(np.mean([-math.log(max(1e-9, f(r)[np.argmax(r["won"])])) for r in rs]))
    res = {"races": len(races), "train": len(train), "test": len(test), "test_from": cut}
    res["win_log_loss"] = {"morning price": win_ll(test, lambda r: chances(r["morning"])),
                           "SP": win_ll(test, lambda r: chances(r["sp"]))}

    # 2. ranking model on the morning price
    logp, X, mask, y = pad(train)
    th0 = np.concatenate([[1.0], np.zeros(len(FEATURES))])
    fit = minimize(nll, th0, args=(logp, X, mask, y), jac=True, method="L-BFGS-B")
    theta = fit.x
    res["win_log_loss"]["morning + horse record"] = win_ll(test, lambda r: model_p(theta, r))
    res["weights"] = {"morning price (a)": round(float(theta[0]), 4),
                      **{f: round(float(b), 4) for f, b in zip(FEATURES, theta[1:])}}

    # place: Brier of top-k from each, where Betfair's place market says who placed
    pl = [r for r in test if r["placed"] is not None][:6000]
    briers = defaultdict(list)
    for r in pl:
        for label, p in (("morning price", chances(r["morning"])), ("SP", chances(r["sp"])),
                         ("morning + horse record", model_p(theta, r))):
            briers[label].extend(((harville_topk(p, r["k"]) - r["placed"]) ** 2).tolist())
    res["place_brier"] = {k: float(np.mean(v)) for k, v in briers.items()}

    # 3. price moves: log(morning / SP) > 0 means it shortened
    def move_xy(rs):
        Xm = np.vstack([np.column_stack([np.log(chances(r["morning"])), r["X"]]) for r in rs])
        ym = np.concatenate([np.log(r["morning"] / r["sp"]) for r in rs])
        return np.column_stack([np.ones(len(Xm)), Xm]), ym
    Xa, ya = move_xy(train)
    coef = np.linalg.lstsq(Xa, ya, rcond=None)[0]
    Xt, yt = move_xy(test)
    pred = Xt @ coef
    base = Xt[:, :2] @ np.linalg.lstsq(Xa[:, :2], ya, rcond=None)[0]
    r2 = lambda yhat: float(1 - ((yt - yhat) ** 2).sum() / ((yt - yt.mean()) ** 2).sum())  # noqa: E731
    res["price_moves"] = {"r2_price_only": r2(base), "r2_with_horse_record": r2(pred),
                          "shortened_share": float((yt > 0).mean()),
                          "picked_by_model_shortened": float((yt[pred > np.quantile(pred, 0.9)] > 0).mean())}

    # 4. paper win bets at the morning price
    bets = []
    for r in test:
        p = model_p(theta, r)
        for i in range(len(p)):
            o = r["morning"][i]
            if p[i] * (1 + (o - 1) * (1 - COMMISSION)) > 1 + EDGE:
                profit = (o - 1) * (1 - COMMISSION) if r["won"][i] else -1.0
                bets.append((profit, o / r["sp"][i] - 1, o))
    allb = [((r["morning"][i] - 1) * (1 - COMMISSION) if r["won"][i] else -1.0) for r in test for i in range(len(r["won"]))]
    res["paper_win_bets"] = {
        "bets": len(bets), "roi": float(np.mean([b[0] for b in bets])) if bets else None,
        "beat_sp": float(np.mean([b[1] > 0 for b in bets])) if bets else None,
        "avg_price": float(np.median([b[2] for b in bets])) if bets else None,
        "every_runner_roi": float(np.mean(allb))}

    print("\n=== win: log loss on the test months (lower is better) ===")
    for k, v in res["win_log_loss"].items():
        print(f"  {k:<24} {v:.4f}")
    print("\n=== place: Brier score where Betfair's place market says who placed (lower is better) ===")
    for k, v in res["place_brier"].items():
        print(f"  {k:<24} {v:.5f}")
    print("\n=== learned weights (features standardised) ===")
    for k, v in res["weights"].items():
        print(f"  {k:<24} {v:+.4f}")
    m = res["price_moves"]
    print("\n=== morning -> SP price moves ===")
    print(f"  explained by the morning price alone: {100 * m['r2_price_only']:.2f}%  with horse record: "
          f"{100 * m['r2_with_horse_record']:.2f}%")
    print(f"  horses that shortened: {100 * m['shortened_share']:.1f}%; of the model's top 10% picks: "
          f"{100 * m['picked_by_model_shortened']:.1f}%")
    b = res["paper_win_bets"]
    print("\n=== paper win bets at the morning price (model 5%+ over the price, 2% commission) ===")
    if b["bets"]:
        print(f"  {b['bets']} bets, return {100 * b['roi']:+.1f}%, beat SP {100 * b['beat_sp']:.0f}%, "
              f"median price {b['avg_price']:.1f}  (backing every runner: {100 * b['every_runner_roi']:+.1f}%)")
    else:
        print("  none")
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stables_morning_test.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
