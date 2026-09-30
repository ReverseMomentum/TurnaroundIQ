"""
FTA path model (V5) — the full event, built point-in-time.

    FTA% = P(team goes 2 goals up)  x  P(team fails to win | went 2 up)
           (stage A, all team-sides)   (stage B, sides that went 2 up)

Every feature is computed only from matches played BEFORE the match being
scored (exponentially decayed, shrunk towards the league average), so the
walk-forward numbers are honest and training matches what the app sees.

    python -u models/fta_path_model.py train          # fit + save fta_path_model.pkl
    python -u models/fta_path_model.py walk-forward   # chronological check vs baseline

Serving: predict_fixture(team, opponent, league, is_home) rebuilds team
state from the DB (cached STATE_TTL seconds), so new live results count
immediately without retraining.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import get_db
from team_normalizer import normalize_team

MODEL_FILE = PROJECT_ROOT / "fta_path_model.pkl"
VERSION = "V5-path"
HALF_LIFE_DAYS = 365.0
EARLY_MINUTE = 30
STATE_TTL = 3600
MIN_ROWS_A = 2000

# Shrinkage strength (pseudo-observations of the league average)
K_RATE = 10.0      # per-match rates (2-up, early goals, …)
K_COND = 12.0      # rates conditional on going 2-up / 2-down (rarer)
K_MINUTE = 5.0

FEATURES = [
    "is_home",
    "t_2up_rate", "o_2down_rate",
    "t_fail_rate", "o_rescue_rate",
    "t_2up_minute",
    "t_gf", "t_ga", "o_gf", "o_ga",
    "t_early_for", "o_early_against",
    "t_ht_diff", "o_ht_diff",
    "t_lead_keep", "o_lead_keep",
    "lg_2up_rate", "lg_fail_rate", "lg_2up_minute", "lg_goals",
    "t_log_n", "o_log_n",
    "naive_path",
]
# Market odds (de-margined 1X2 probabilities from the team's point of view).
# Only used by the odds experiment until a live odds feed exists.
ODDS_FEATURES = ["mkt_win", "mkt_draw", "mkt_lose"]

_state_cache = {"ts": 0.0, "teams": None, "leagues": None}
_bundle_cache = None


# --- data ---------------------------------------------------------------------

def _day(value):
    try:
        return date.fromisoformat(str(value)[:10]).toordinal()
    except (TypeError, ValueError):
        return None


def _side_outcomes(goals, fh, fa):
    """goals: [(minute, side)] chronological -> per-side outcome dicts."""
    hs = as_ = 0
    out = {1: {"up2": 0, "minute": None, "early_for": 0, "ht_for": 0, "led": 0},
           2: {"up2": 0, "minute": None, "early_for": 0, "ht_for": 0, "led": 0}}
    for minute, side in goals:
        minute = int(minute or 0)
        if side == 1:
            hs += 1
        elif side == 2:
            as_ += 1
        else:
            continue
        if minute <= EARLY_MINUTE:
            out[side]["early_for"] += 1
        if minute <= 45:
            out[side]["ht_for"] += 1
        if hs > as_:
            out[1]["led"] = 1
        if as_ > hs:
            out[2]["led"] = 1
        if hs - as_ >= 2 and not out[1]["up2"]:
            out[1]["up2"], out[1]["minute"] = 1, minute
        if as_ - hs >= 2 and not out[2]["up2"]:
            out[2]["up2"], out[2]["minute"] = 1, minute
    return out


def load_matches(conn=None):
    """All finished matches (historical + live), chronological, deduped."""
    own = conn is None
    conn = conn or get_db()
    matches = {}
    odds = {}
    try:
        odds = {mid: (h, d, a) for mid, h, d, a in conn.execute(
            "SELECT match_id, odds_h, odds_d, odds_a FROM match_odds")}
    except Exception:
        pass  # no odds collected (collectors/odds_history_fd.py)
    try:
        events = defaultdict(list)
        for mid, minute, side in conn.execute(
            "SELECT match_id, minute, side FROM historical_events "
            "WHERE is_goal = 1 ORDER BY match_id, minute"
        ):
            events[mid].append((minute, side))
        for mid, d, league, home, away, fh, fa in conn.execute(
            "SELECT match_id, date, league, home_team, away_team, final_home, final_away "
            "FROM historical_matches"
        ):
            day = _day(d)
            if day is None or fh is None or fa is None:
                continue
            goals = events.get(mid, [])
            if len(goals) != int(fh) + int(fa):
                continue  # timeline doesn't reproduce the score — unusable
            home, away = normalize_team(home), normalize_team(away)
            matches[(day, home, away)] = {
                "day": day, "league": league or "", "home": home, "away": away,
                "fh": int(fh), "fa": int(fa), "sides": _side_outcomes(goals, fh, fa),
                "odds": odds.get(mid),
            }
    except Exception as exc:
        print(f"[path-model] historical tables unavailable: {exc}")

    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(match_results)")}
        date_expr = "COALESCE(match_date, processed_at)" if "match_date" in cols else "processed_at"
        rows = conn.execute(
            f"""SELECT {date_expr}, league, home_team, away_team, final_home, final_away,
                   home_2up, away_2up, home_lead_minute, away_lead_minute,
                   home_early_goal, away_early_goal,
                   home_first_half_for, away_first_half_for, home_led, away_led
               FROM match_results"""
        ).fetchall()
        for (d, league, home, away, fh, fa, h2, a2, hm, am,
             he, ae, hht, aht, hl, al) in rows:
            day = _day(d)
            if day is None or fh is None or fa is None:
                continue
            home, away = normalize_team(home), normalize_team(away)
            key = (day, home, away)
            if key in matches:
                continue
            matches[key] = {
                "day": day, "league": league or "", "home": home, "away": away,
                "fh": int(fh), "fa": int(fa),
                "sides": {
                    1: {"up2": int(h2 or 0), "minute": hm if h2 else None,
                        "early_for": int(he or 0), "ht_for": int(hht or 0), "led": int(hl or 0)},
                    2: {"up2": int(a2 or 0), "minute": am if a2 else None,
                        "early_for": int(ae or 0), "ht_for": int(aht or 0), "led": int(al or 0)},
                },
            }
    except Exception as exc:
        print(f"[path-model] match_results unavailable: {exc}")
    if own:
        conn.close()
    return sorted(matches.values(), key=lambda m: (m["day"], m["home"]))


# --- decayed team / league state ------------------------------------------------

TEAM_KEYS = ("n", "up2", "fail", "minute_sum", "down2", "rescue", "gf", "ga",
             "early_for", "early_against", "ht_for", "ht_against", "led", "led_kept")


class Decayed:
    __slots__ = ("day", "raw_n") + TEAM_KEYS

    def __init__(self):
        self.day = None
        self.raw_n = 0
        for k in TEAM_KEYS:
            setattr(self, k, 0.0)

    def decay_to(self, day, half_life=HALF_LIFE_DAYS):
        if self.day is not None and day > self.day:
            f = 0.5 ** ((day - self.day) / half_life)
            for k in TEAM_KEYS:
                setattr(self, k, getattr(self, k) * f)
        if self.day is None or day > self.day:
            self.day = day

    def add(self, **vals):
        self.raw_n += 1
        for k, v in vals.items():
            setattr(self, k, getattr(self, k) + v)


def _shrink(num, den, prior, k):
    return (num + k * prior) / (den + k)


def _league_rates(lg):
    n = max(lg.n, 1e-9)
    up2 = lg.up2 / n if lg.n else 0.27
    fail = lg.fail / lg.up2 if lg.up2 else 0.08
    minute = lg.minute_sum / lg.up2 if lg.up2 else 55.0
    goals = lg.gf / n if lg.n else 1.4
    early = lg.early_for / n if lg.n else 0.3
    keep = lg.led_kept / lg.led if lg.led else 0.6
    return {"up2": up2, "fail": fail, "minute": minute,
            "goals": goals, "early": early, "keep": keep}


def features_for(t, o, lg, is_home):
    """Pre-match features for team state t vs opponent o in league lg."""
    L = _league_rates(lg)
    t_2up = _shrink(t.up2, t.n, L["up2"], K_RATE)
    o_2down = _shrink(o.down2, o.n, L["up2"], K_RATE)
    t_fail = _shrink(t.fail, t.up2, L["fail"], K_COND)
    o_rescue = _shrink(o.rescue, o.down2, L["fail"], K_COND)
    return {
        "is_home": int(bool(is_home)),
        "t_2up_rate": t_2up,
        "o_2down_rate": o_2down,
        "t_fail_rate": t_fail,
        "o_rescue_rate": o_rescue,
        "t_2up_minute": _shrink(t.minute_sum, t.up2, L["minute"], K_MINUTE),
        "t_gf": _shrink(t.gf, t.n, L["goals"], K_RATE),
        "t_ga": _shrink(t.ga, t.n, L["goals"], K_RATE),
        "o_gf": _shrink(o.gf, o.n, L["goals"], K_RATE),
        "o_ga": _shrink(o.ga, o.n, L["goals"], K_RATE),
        "t_early_for": _shrink(t.early_for, t.n, L["early"], K_RATE),
        "o_early_against": _shrink(o.early_against, o.n, L["early"], K_RATE),
        "t_ht_diff": _shrink(t.ht_for - t.ht_against, t.n, 0.0, K_RATE),
        "o_ht_diff": _shrink(o.ht_for - o.ht_against, o.n, 0.0, K_RATE),
        "t_lead_keep": _shrink(t.led_kept, t.led, L["keep"], K_RATE),
        "o_lead_keep": _shrink(o.led_kept, o.led, L["keep"], K_RATE),
        "lg_2up_rate": L["up2"],
        "lg_fail_rate": L["fail"],
        "lg_2up_minute": L["minute"],
        "lg_goals": L["goals"],
        "t_log_n": math.log1p(t.raw_n),
        "o_log_n": math.log1p(o.raw_n),
        "naive_path": math.sqrt(max(t_2up * o_2down, 0.0)) * (t_fail + o_rescue) / 2,
    }


def _update(teams, leagues, m):
    day = m["day"]
    lg = leagues[m["league"]]
    for side, team, opp_side, gf, ga in ((1, m["home"], 2, m["fh"], m["fa"]),
                                         (2, m["away"], 1, m["fa"], m["fh"])):
        s, o = m["sides"][side], m["sides"][opp_side]
        won = gf > ga
        vals = dict(
            n=1, up2=s["up2"], fail=int(bool(s["up2"]) and not won),
            minute_sum=(float(s["minute"]) if s["up2"] and s["minute"] else 0.0),
            down2=o["up2"], rescue=int(bool(o["up2"]) and gf >= ga),
            gf=gf, ga=ga, early_for=min(s["early_for"], 1),
            early_against=min(o["early_for"], 1),
            ht_for=s["ht_for"], ht_against=o["ht_for"],
            led=s["led"], led_kept=int(bool(s["led"]) and won),
        )
        teams[team].decay_to(day)
        teams[team].add(**vals)
        lg.decay_to(day)
        lg.add(**vals)


def _odds_features(odds, side):
    """De-margined market probabilities for this side; NaN when unknown."""
    nan = float("nan")
    try:
        inv = [1.0 / float(x) for x in odds]
    except (TypeError, ValueError, ZeroDivisionError):
        return {"mkt_win": nan, "mkt_draw": nan, "mkt_lose": nan, "has_odds": 0}
    total = sum(inv)
    ph, pd, pa = (x / total for x in inv)
    win, lose = (ph, pa) if side == 1 else (pa, ph)
    return {"mkt_win": win, "mkt_draw": pd, "mkt_lose": lose, "has_odds": 1}


def replay(matches, collect=True):
    """
    Walk matches in date order. Features for each side use state BEFORE the
    match; state is updated after. Returns (rows, teams, leagues).
    rows: dicts with FEATURES + day, up2, fail, team, league.
    """
    teams = defaultdict(Decayed)
    leagues = defaultdict(Decayed)
    rows = []
    for m in matches:
        day = m["day"]
        if collect:
            lg = leagues[m["league"]]
            lg.decay_to(day)
            for side, team, opp, is_home, won in (
                (1, m["home"], m["away"], 1, m["fh"] > m["fa"]),
                (2, m["away"], m["home"], 0, m["fa"] > m["fh"]),
            ):
                t, o = teams[team], teams[opp]
                t.decay_to(day)
                o.decay_to(day)
                f = features_for(t, o, lg, is_home)
                s = m["sides"][side]
                f.update(day=day, team=team, league=m["league"],
                         up2=int(s["up2"]), fail=int(bool(s["up2"]) and not won))
                f.update(_odds_features(m.get("odds"), side))
                rows.append(f)
        _update(teams, leagues, m)
    return rows, teams, leagues


# --- fitting ------------------------------------------------------------------------

def _xy(rows, target, where=None, feats=None):
    feats = feats or FEATURES
    sel = [r for r in rows if where is None or where(r)]
    X = np.array([[r[f] for f in feats] for r in sel], dtype=float)
    y = np.array([r[target] for r in sel], dtype=int)
    return X, y, sel


def _logit(p, eps=1e-6):
    p = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    return np.log(p / (1 - p))


def _fit_stage(X, y):
    """
    Regularised logistic regression on standardised features. Chosen over
    gradient boosting after testing: the conditional stage (fail once 2-up)
    has few positives and boosting fitted noise; the linear model ranked
    better out of time and needs no separate calibration.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))
    model.fit(X, y)
    return model, None


def _predict_stage(model, cal, X):
    p = model.predict_proba(X)[:, 1]
    if cal is not None:
        p = cal.predict_proba(_logit(p).reshape(-1, 1))[:, 1]
    return p


def _metrics(y, p):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    y = np.asarray(y)
    p = np.asarray(p)
    out = {"n": int(len(y)), "actual": float(y.mean()) if len(y) else 0.0,
           "pred": float(p.mean()) if len(p) else 0.0,
           "brier": float(brier_score_loss(y, p)) if len(y) else None}
    try:
        out["auc"] = float(roc_auc_score(y, p))
    except ValueError:
        out["auc"] = None
    return out


def train(save=True):
    matches = load_matches()
    rows, _, _ = replay(matches)
    Xa, ya, _ = _xy(rows, "up2")
    Xb, yb, _ = _xy(rows, "fail", where=lambda r: r["up2"] == 1)
    print(f"matches {len(matches)}  sides {len(ya)}  went 2-up {len(yb)} "
          f"({100 * ya.mean():.1f}%)  failed to win once 2-up {100 * yb.mean():.1f}%")
    if len(ya) < MIN_ROWS_A:
        raise SystemExit(f"Only {len(ya)} team-sides — need {MIN_ROWS_A}. Run the historical pipeline.")
    model_a, cal_a = _fit_stage(Xa, ya)
    model_b, cal_b = _fit_stage(Xb, yb)
    bundle = {
        "version": VERSION,
        "features": FEATURES,
        "model_a": model_a, "cal_a": cal_a,
        "model_b": model_b, "cal_b": cal_b,
        "half_life_days": HALF_LIFE_DAYS,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "rows_a": int(len(ya)), "rows_b": int(len(yb)),
        "base_2up": float(ya.mean()), "base_fail": float(yb.mean()),
        "base_full": float(np.mean([r["fail"] for r in rows])),
    }
    holdout = _holdout_score(rows)
    bundle["holdout"] = holdout
    print(f"held-out (latest 15%): full-event AUC {holdout['auc']:.3f}  "
          f"Brier {holdout['brier']:.4f}  skill vs flat rate {100 * holdout['skill']:+.1f}%")
    if save:
        joblib.dump(bundle, MODEL_FILE)
        global _bundle_cache
        _bundle_cache = bundle
        print(f"saved {MODEL_FILE.name} ({VERSION})")
        try:
            from models.importance_store import save_model_run_with_importance
            save_model_run_with_importance(
                model_name="FTA_PATH", version=VERSION,
                training_rows=int(len(ya)), brier_score=holdout["brier"],
                log_loss=holdout["log_loss"], roc_auc=holdout["auc"],
                notes=(f"full event = P(2up) x P(fail|2up); held-out latest 15%; "
                       f"skill vs flat {100 * holdout['skill']:+.1f}%"),
            )
        except Exception as exc:
            print(f"[path-model] could not record model run: {exc}")
    return bundle


def _holdout_score(rows, frac=0.15):
    """Fit on the earliest 85% of team-sides, score the full event on the rest."""
    from sklearn.metrics import brier_score_loss, log_loss

    rows = sorted(rows, key=lambda r: r["day"])
    cut = int(len(rows) * (1 - frac))
    train_rows, test_rows = rows[:cut], rows[cut:]
    Xa, ya, _ = _xy(train_rows, "up2")
    Xb, yb, _ = _xy(train_rows, "fail", where=lambda r: r["up2"] == 1)
    ma, ca = _fit_stage(Xa, ya)
    mb, cb = _fit_stage(Xb, yb)
    Xt, _, sel = _xy(test_rows, "up2")
    p = _predict_stage(ma, ca, Xt) * _predict_stage(mb, cb, Xt)
    y = np.array([r["fail"] for r in sel])
    m = _metrics(y, p)
    flat = float(np.mean([r["fail"] for r in train_rows]))
    brier_flat = float(brier_score_loss(y, np.full_like(p, flat)))
    return {
        "auc": m["auc"] or 0.5, "brier": m["brier"],
        "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "skill": 1 - m["brier"] / brier_flat if brier_flat else 0.0,
        "n": int(len(y)),
    }


# --- walk-forward -----------------------------------------------------------------

FULL_BANDS = [0.0, 1.0, 2.0, 3.0, 4.0, 100.0]


def _walk(rows, feats, folds=5, min_train_frac=0.3, verbose=True):
    """Expanding-window walk-forward. Returns (fold results, pooled y, pooled p)."""
    from sklearn.metrics import brier_score_loss

    rows = sorted(rows, key=lambda r: r["day"])
    n = len(rows)
    start = int(n * min_train_frac)
    edges = [start + (n - start) * i // folds for i in range(folds + 1)]
    pooled_y, pooled_p, results = [], [], []
    for k in range(folds):
        train_rows, test_rows = rows[:edges[k]], rows[edges[k]:edges[k + 1]]
        Xa, ya, _ = _xy(train_rows, "up2", feats=feats)
        Xb, yb, _ = _xy(train_rows, "fail", where=lambda r: r["up2"] == 1, feats=feats)
        ma, ca = _fit_stage(Xa, ya)
        mb, cb = _fit_stage(Xb, yb)
        Xt, _, sel = _xy(test_rows, "up2", feats=feats)
        pa = _predict_stage(ma, ca, Xt)
        pb = _predict_stage(mb, cb, Xt)
        full = pa * pb
        y_full = np.array([r["fail"] for r in sel])
        y_a = np.array([r["up2"] for r in sel])
        m_full = _metrics(y_full, full)
        m_a = _metrics(y_a, pa)
        twoup = y_a == 1
        m_b = _metrics(y_full[twoup], pb[twoup])
        base_rate = float(np.mean([r["fail"] for r in train_rows]))
        brier_base = float(brier_score_loss(y_full, np.full_like(full, base_rate)))
        skill = 1 - m_full["brier"] / brier_base if brier_base else 0.0
        d0 = date.fromordinal(test_rows[0]["day"]).isoformat()
        d1 = date.fromordinal(test_rows[-1]["day"]).isoformat()
        results.append({"from": d0, "to": d1, "full": m_full, "a": m_a, "b": m_b,
                        "skill": skill})
        pooled_y.extend(y_full)
        pooled_p.extend(full)
        if verbose:
            print(f"fold {k + 1}: {d0}→{d1}  sides={m_full['n']}  "
                  f"full actual={100 * m_full['actual']:.2f}% pred={100 * m_full['pred']:.2f}%  "
                  f"AUC full={m_full['auc']:.3f} 2up={m_a['auc']:.3f} "
                  f"fail|2up={m_b['auc'] or float('nan'):.3f}  "
                  f"skill vs flat rate={100 * skill:+.1f}%")
    return results, np.array(pooled_y), np.array(pooled_p)


def _top_lift(y, p, frac=0.1):
    order = np.argsort(-p)
    top = order[: max(1, int(len(order) * frac))]
    return float(p[top].mean()), float(y[top].mean()), float(y[top].mean() / max(y.mean(), 1e-9))


def walk_forward(folds=5, min_train_frac=0.3):
    rows, _, _ = replay(load_matches())
    if len(rows) < MIN_ROWS_A:
        raise SystemExit(f"Only {len(rows)} team-sides — need {MIN_ROWS_A}.")
    results, y, p = _walk(rows, FEATURES, folds, min_train_frac)
    p = p * 100
    print("\nCalibration (all test folds) — predicted full-event % vs what happened")
    print("  band      |     n  | predicted | actual")
    for lo, hi in zip(FULL_BANDS[:-1], FULL_BANDS[1:]):
        mask = (p >= lo) & (p < hi)
        if mask.sum():
            print(f"  {lo:>3.0f}-{hi:<4.0f}% | {mask.sum():>6} | {p[mask].mean():>8.2f}% | "
                  f"{100 * y[mask].mean():>5.2f}%")
    pred, hit, lift = _top_lift(y, p / 100)
    print(f"\nTop 10% of picks: predicted {100 * pred:.2f}%, happened {100 * hit:.2f}% "
          f"(overall {100 * y.mean():.2f}%, lift x{lift:.2f})")
    aucs = [r["full"]["auc"] for r in results if r["full"]["auc"] is not None]
    print(f"Mean AUC (full event) {np.mean(aucs):.3f} ±{np.std(aucs):.3f}; "
          f"mean skill vs flat rate {100 * np.mean([r['skill'] for r in results]):+.1f}%")
    return results


def odds_test(folds=5, min_train_frac=0.3):
    """
    Does adding market odds improve the model? Same matches, same folds,
    with and without odds features. Only matches with linked odds are used.
    """
    rows, _, _ = replay(load_matches())
    with_odds = [r for r in rows if r.get("has_odds")]
    cover = 100 * len(with_odds) / max(len(rows), 1)
    print(f"team-sides with odds: {len(with_odds)} of {len(rows)} ({cover:.0f}%)")
    if len(with_odds) < MIN_ROWS_A:
        raise SystemExit("Not enough matches with odds — run collectors/odds_history_fd.py")

    summary = {}
    for label, feats in (("without odds", FEATURES), ("with odds", FEATURES + ODDS_FEATURES)):
        res, y, p = _walk(with_odds, feats, folds, min_train_frac, verbose=False)
        pred, hit, lift = _top_lift(y, p)
        summary[label] = {
            "auc_full": float(np.mean([r["full"]["auc"] for r in res])),
            "auc_2up": float(np.mean([r["a"]["auc"] for r in res])),
            "auc_fail": float(np.mean([r["b"]["auc"] for r in res if r["b"]["auc"]])),
            "skill": float(np.mean([r["skill"] for r in res])),
            "top_hit": hit, "lift": lift, "base": float(y.mean()),
        }

    a, b = summary["without odds"], summary["with odds"]
    print("\n                              without odds   with odds")
    print(f"  AUC going 2-up              {a['auc_2up']:>10.3f}   {b['auc_2up']:>9.3f}")
    print(f"  AUC fail once 2-up          {a['auc_fail']:>10.3f}   {b['auc_fail']:>9.3f}")
    print(f"  AUC full event              {a['auc_full']:>10.3f}   {b['auc_full']:>9.3f}")
    print(f"  top 10% happened            {100 * a['top_hit']:>9.2f}%   {100 * b['top_hit']:>8.2f}%")
    print(f"  top 10% lift vs average     {a['lift']:>9.2f}x   {b['lift']:>8.2f}x")
    print(f"  skill vs flat rate          {100 * a['skill']:>+9.1f}%   {100 * b['skill']:>+8.1f}%")
    gain = b["auc_full"] - a["auc_full"]
    verdict = ("worth it" if gain >= 0.02 or b["lift"] - a["lift"] >= 0.15
               else "marginal" if gain >= 0.005 else "not worth it")
    print(f"\nVerdict: odds add {gain:+.3f} AUC on the full event -> {verdict}")
    return summary


# --- serving ------------------------------------------------------------------------

def load_bundle():
    global _bundle_cache
    if _bundle_cache is None:
        if not MODEL_FILE.is_file():
            return None
        _bundle_cache = joblib.load(MODEL_FILE)
    return _bundle_cache


def current_state(force=False):
    now = time.time()
    if force or _state_cache["teams"] is None or now - _state_cache["ts"] > STATE_TTL:
        _, teams, leagues = replay(load_matches(), collect=False)
        _state_cache.update(ts=now, teams=teams, leagues=leagues)
    return _state_cache["teams"], _state_cache["leagues"]


def data_confidence(t, o):
    """0–100: how much match history backs this pick (not a probability)."""
    depth = min(t.raw_n, o.raw_n)
    return round(20 + 65 * min(1.0, depth / 60.0), 1)


def predict_fixture(team, opponent, league, is_home, as_of=None):
    """None if no trained model; else the full-event breakdown in percent."""
    bundle = load_bundle()
    if bundle is None:
        return None
    teams, leagues = current_state()
    day = _day(as_of) if as_of else date.today().toordinal()
    t = teams.get(normalize_team(team)) or Decayed()
    o = teams.get(normalize_team(opponent)) or Decayed()
    lg = leagues.get(league or "") or Decayed()
    t2, o2, lg2 = _copy(t), _copy(o), _copy(lg)  # keep cached state untouched
    for s in (t2, o2, lg2):
        if s.day is not None:
            s.decay_to(day)
    f = features_for(t2, o2, lg2, is_home)
    X = np.array([[f[k] for k in bundle["features"]]], dtype=float)
    pa = float(_predict_stage(bundle["model_a"], bundle["cal_a"], X)[0])
    pb = float(_predict_stage(bundle["model_b"], bundle["cal_b"], X)[0])
    return {
        "two_up_pct": round(100 * pa, 2),
        "fail_given_2up_pct": round(100 * pb, 2),
        "fta_pct": round(100 * pa * pb, 2),
        "usual_2up_minute": round(f["t_2up_minute"], 1),
        "data_confidence": data_confidence(t, o),
        "model_version": bundle["version"],
    }


def _copy(s):
    c = Decayed()
    c.day, c.raw_n = s.day, s.raw_n
    for k in TEAM_KEYS:
        setattr(c, k, getattr(s, k))
    return c


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["train", "walk-forward", "odds-test"])
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args(argv)
    if args.command == "train":
        train()
    elif args.command == "odds-test":
        odds_test(folds=args.folds)
    else:
        walk_forward(folds=args.folds)


if __name__ == "__main__":
    main()
