"""
FTA path model (V6) — the full event, built point-in-time, calibrated.

    FTA% = P(team goes 2 goals up)  x  P(team fails to win | went 2 up)
           (stage A, all team-sides)   (stage B, sides that went 2 up)

Every feature is computed only from matches played BEFORE the match being
scored (exponentially decayed, shrunk towards the league average), so the
walk-forward numbers are honest and training matches what the app sees.

    python -u models/fta_path_model.py train          # fit + save fta_path_model.pkl
    python -u models/fta_path_model.py walk-forward   # chronological check vs baseline
    python -u models/fta_path_model.py compare        # base vs +behaviour vs +over/under

Training tests each candidate input set on the same held-back matches and keeps
an addition only if it improves out-of-sample log loss. It does the same for
recency weighting (recent seasons counting more when fitting, because the FTA
rate has drifted upwards). The full-event FTA% is then calibrated (Platt scaling
fitted on walk-forward, out-of-sample predictions, recency-weighted if that
predicts the latest period better) so a displayed 2.4% means roughly 2.4% of
such games turn around.

Serving: predict_fixture(team, opponent, league, is_home) rebuilds team
state from the DB (cached STATE_TTL seconds), so new live results count
immediately without retraining.
"""

from __future__ import annotations

import argparse
import math
import sys
import threading
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
VERSION = "V6-path"
HALF_LIFE_DAYS = 365.0
# Training-time recency weighting: a match this many days older than the newest
# counts half as much when fitting and calibrating. train() tries each option on
# the held-back latest matches and keeps one only if it predicts them better.
RECENCY_OPTIONS = [None, 1460.0, 730.0]  # None = every season counts the same
EARLY_MINUTE = 30
LATE_MINUTE = 75        # "late" goals: 76th minute onwards
EARLY_2UP_MINUTE = 60   # 2-ups before this leave the opponent lots of time
STATE_TTL = 3600
MIN_ROWS_A = 2000

# Shrinkage strength (pseudo-observations of the league average)
K_RATE = 10.0      # per-match rates (2-up, early goals, …)
K_COND = 12.0      # rates conditional on going 2-up / 2-down (rarer)
K_MINUTE = 5.0

BASE_FEATURES = [
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
# How teams behave around leads (mostly informs stage B: fail once 2-up).
BEHAVIOUR_FEATURES = [
    "t_late_ga",      # goals the team concedes from the 76th minute, per match
    "o_late_gf",      # goals the opponent scores from the 76th minute, per match
    "t_lead_pts",     # points the team takes from matches it led
    "o_trail_pts",    # points the opponent takes from matches it trailed
    "o_chase_gf",     # goals the opponent scores while behind, per match
    "t_2up_early",    # share of the team's 2-up leads that came before the hour
]
# Market's over/under 2.5 goals view (de-margined P(over)); only where quoted.
OU_FEATURES = ["mkt_over25"]
FEATURES = BASE_FEATURES  # default until train() picks a set
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
    blank = {"up2": 0, "minute": None, "early_for": 0, "ht_for": 0, "led": 0,
             "late_for": 0, "chase_for": 0, "timeline": 1}
    out = {1: dict(blank), 2: dict(blank)}
    for minute, side in goals:
        minute = int(minute or 0)
        if side not in (1, 2):
            continue
        if (side == 1 and hs < as_) or (side == 2 and as_ < hs):
            out[side]["chase_for"] += 1
        if minute > LATE_MINUTE:
            out[side]["late_for"] += 1
        if side == 1:
            hs += 1
        else:
            as_ += 1
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
    ou = {}
    try:
        odds = {mid: (h, d, a) for mid, h, d, a in conn.execute(
            "SELECT match_id, odds_h, odds_d, odds_a FROM match_odds")}
        cols = {r[1] for r in conn.execute("PRAGMA table_info(match_odds)")}
        if "over25" in cols:
            ou = {mid: (o, u) for mid, o, u in conn.execute(
                "SELECT match_id, over25, under25 FROM match_odds WHERE over25 IS NOT NULL")}
    except Exception:
        pass  # no odds collected (collectors/odds_history_fd.py)
    live_goals = defaultdict(list)
    try:
        for mid, minute, side in conn.execute(
            "SELECT match_id, minute, side FROM live_goals ORDER BY match_id, minute"
        ):
            live_goals[str(mid)].append((minute, side))
    except Exception:
        pass  # older installs: live results have no goal timelines yet
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
                "odds": odds.get(mid), "ou": ou.get(mid), "source": "historical",
                "goals": list(goals),
            }
    except Exception as exc:
        print(f"[path-model] historical tables unavailable: {exc}")

    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(match_results)")}
        date_expr = "COALESCE(match_date, processed_at)" if "match_date" in cols else "processed_at"
        rows = conn.execute(
            f"""SELECT match_id, {date_expr}, league, home_team, away_team, final_home, final_away,
                   home_2up, away_2up, home_lead_minute, away_lead_minute,
                   home_early_goal, away_early_goal,
                   home_first_half_for, away_first_half_for, home_led, away_led
               FROM match_results"""
        ).fetchall()
        for (mid, d, league, home, away, fh, fa, h2, a2, hm, am,
             he, ae, hht, aht, hl, al) in rows:
            day = _day(d)
            if day is None or fh is None or fa is None:
                continue
            home, away = normalize_team(home), normalize_team(away)
            key = (day, home, away)
            if key in matches:
                continue
            timeline = live_goals.get(str(mid), [])
            # 0-0 has an empty timeline that is still complete
            goals = None
            if (timeline or int(fh) + int(fa) == 0) and len(timeline) == int(fh) + int(fa):
                sides = _side_outcomes(timeline, fh, fa)
                goals = list(timeline)
            else:  # summary only: behaviour features that need goal minutes skip it
                sides = {
                    1: {"up2": int(h2 or 0), "minute": hm if h2 else None,
                        "early_for": int(he or 0), "ht_for": int(hht or 0), "led": int(hl or 0),
                        "late_for": 0, "chase_for": 0, "timeline": 0},
                    2: {"up2": int(a2 or 0), "minute": am if a2 else None,
                        "early_for": int(ae or 0), "ht_for": int(aht or 0), "led": int(al or 0),
                        "late_for": 0, "chase_for": 0, "timeline": 0},
                }
            matches[key] = {
                "day": day, "league": league or "", "home": home, "away": away,
                "fh": int(fh), "fa": int(fa), "sides": sides,
                "source": "live" + ("" if sides[1].get("timeline") else " (no timeline)"),
                "goals": goals,
            }
    except Exception as exc:
        print(f"[path-model] match_results unavailable: {exc}")
    if own:
        conn.close()
    return sorted(matches.values(), key=lambda m: (m["day"], m["home"]))


# --- decayed team / league state ------------------------------------------------

TEAM_KEYS = ("n", "up2", "fail", "minute_sum", "down2", "rescue", "gf", "ga",
             "early_for", "early_against", "ht_for", "ht_against", "led", "led_kept",
             # behaviour (tl_n = matches with a goal timeline)
             "tl_n", "late_gf", "late_ga", "chase_gf", "led_pts", "trailed", "trail_pts",
             "up2_early")


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
    tl = lg.tl_n
    return {"up2": up2, "fail": fail, "minute": minute,
            "goals": goals, "early": early, "keep": keep,
            "late": lg.late_gf / tl if tl else 0.3,
            "chase": lg.chase_gf / tl if tl else 0.25,
            "lead_pts": lg.led_pts / lg.led if lg.led else 2.2,
            "trail_pts": lg.trail_pts / lg.trailed if lg.trailed else 0.6,
            "up2_early": lg.up2_early / lg.up2 if lg.up2 else 0.5}


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
        "t_late_ga": _shrink(t.late_ga, t.tl_n, L["late"], K_RATE),
        "o_late_gf": _shrink(o.late_gf, o.tl_n, L["late"], K_RATE),
        "t_lead_pts": _shrink(t.led_pts, t.led, L["lead_pts"], K_RATE),
        "o_trail_pts": _shrink(o.trail_pts, o.trailed, L["trail_pts"], K_RATE),
        "o_chase_gf": _shrink(o.chase_gf, o.tl_n, L["chase"], K_RATE),
        "t_2up_early": _shrink(t.up2_early, t.up2, L["up2_early"], K_COND),
    }


def _update(teams, leagues, m):
    day = m["day"]
    lg = leagues[m["league"]]
    for side, team, opp_side, gf, ga in ((1, m["home"], 2, m["fh"], m["fa"]),
                                         (2, m["away"], 1, m["fa"], m["fh"])):
        s, o = m["sides"][side], m["sides"][opp_side]
        won = gf > ga
        pts = 3 if won else 1 if gf == ga else 0
        tl = int(bool(s.get("timeline")))
        vals = dict(
            n=1, up2=s["up2"], fail=int(bool(s["up2"]) and not won),
            minute_sum=(float(s["minute"]) if s["up2"] and s["minute"] else 0.0),
            down2=o["up2"], rescue=int(bool(o["up2"]) and gf >= ga),
            gf=gf, ga=ga, early_for=min(s["early_for"], 1),
            early_against=min(o["early_for"], 1),
            ht_for=s["ht_for"], ht_against=o["ht_for"],
            led=s["led"], led_kept=int(bool(s["led"]) and won),
            tl_n=tl,
            late_gf=s.get("late_for", 0) if tl else 0,
            late_ga=o.get("late_for", 0) if tl else 0,
            chase_gf=s.get("chase_for", 0) if tl else 0,
            led_pts=pts if s["led"] else 0,
            trailed=int(bool(o["led"])),
            trail_pts=pts if o["led"] else 0,
            up2_early=int(bool(s["up2"]) and (s["minute"] or 99) < EARLY_2UP_MINUTE),
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


def _ou_features(ou):
    """De-margined P(over 2.5 goals); NaN when not quoted."""
    try:
        io, iu = 1.0 / float(ou[0]), 1.0 / float(ou[1])
        return {"mkt_over25": io / (io + iu), "has_ou": 1}
    except (TypeError, ValueError, ZeroDivisionError, IndexError):
        return {"mkt_over25": float("nan"), "has_ou": 0}


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
                f.update(_ou_features(m.get("ou")))
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


def recency_weights(days, half_life=None, ref_day=None):
    """0.5 ** (age / half_life), age in days before ref_day (default: newest). None -> all 1."""
    days = np.asarray(days, dtype=float)
    if half_life is None or not len(days):
        return np.ones(len(days))
    ref = days.max() if ref_day is None else ref_day
    return 0.5 ** (np.clip(ref - days, 0, None) / half_life)


def _fit_stage(X, y, w=None):
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
    if w is None:
        model.fit(X, y)
    else:
        model.fit(X, y, logisticregression__sample_weight=w)
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


def _fit_pair(rows, feats, half_life=None):
    Xa, ya, sa = _xy(rows, "up2", feats=feats)
    Xb, yb, sb = _xy(rows, "fail", where=lambda r: r["up2"] == 1, feats=feats)
    ref = max((r["day"] for r in rows), default=0)
    wa = recency_weights([r["day"] for r in sa], half_life, ref) if half_life else None
    wb = recency_weights([r["day"] for r in sb], half_life, ref) if half_life else None
    ma, _ = _fit_stage(Xa, ya, wa)
    mb, _ = _fit_stage(Xb, yb, wb)
    return ma, mb, ya, yb


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


MIN_CAL_SLOPE = 0.25  # calibration may shrink the spread, never flatten or flip the ranking


def platt_fit(y, p, w=None):
    """Two-parameter calibration of full-event probabilities: logit(p') = a*logit(p) + b.

    If the fitted slope is below MIN_CAL_SLOPE (the model barely ranks out of
    sample), the slope is held at the floor and only the level is refitted so the
    average matches reality — picks keep their order instead of collapsing to one number.
    """
    from sklearn.linear_model import LogisticRegression
    y = np.asarray(y, dtype=int)
    z = _logit(p)
    w = np.ones(len(y)) if w is None else np.asarray(w, dtype=float)
    lr = LogisticRegression(C=1e4, max_iter=1000)
    lr.fit(z.reshape(-1, 1), y, sample_weight=w)
    a, b = float(lr.coef_[0][0]), float(lr.intercept_[0])
    if a < MIN_CAL_SLOPE:
        a = MIN_CAL_SLOPE
        target = np.average(y, weights=w)
        lo, hi = -20.0, 20.0
        for _ in range(80):  # bisection: mean(sigmoid(a*z + b)) == observed rate
            b = (lo + hi) / 2
            if np.average(_sigmoid(a * z + b), weights=w) > target:
                hi = b
            else:
                lo = b
    return a, b


def platt_apply(ab, p):
    if not ab:
        return np.asarray(p, dtype=float)
    a, b = ab
    return _sigmoid(a * _logit(p) + b)


def _band_table(y, p, title):
    """Predicted vs actual by predicted-FTA band (p as fractions)."""
    p = np.asarray(p) * 100
    y = np.asarray(y)
    print(title)
    print("  band      |     n  | predicted | actual")
    gap = 0.0
    for lo, hi in zip(FULL_BANDS[:-1], FULL_BANDS[1:]):
        mask = (p >= lo) & (p < hi)
        if mask.sum():
            print(f"  {lo:>3.0f}-{hi:<4.0f}% | {mask.sum():>6} | {p[mask].mean():>8.2f}% | "
                  f"{100 * y[mask].mean():>5.2f}%")
            gap += mask.sum() * abs(p[mask].mean() - 100 * y[mask].mean())
    ece = gap / max(len(p), 1)
    print(f"  average gap between predicted and actual: {ece:.2f} points")
    return ece


def _choose(label_a, ha, label_b, hb):
    """Keep the extra inputs only if they improve out-of-sample log loss without hurting ranking."""
    better = hb["log_loss"] < ha["log_loss"] - 1e-5 and hb["auc"] >= ha["auc"] - 0.002
    print(f"  {label_a:<24} log loss {ha['log_loss']:.5f}  AUC {ha['auc']:.3f}")
    print(f"  {label_b:<24} log loss {hb['log_loss']:.5f}  AUC {hb['auc']:.3f}"
          f"  -> {'KEEP' if better else 'drop'}")
    return better


def _hl_label(half_life):
    return "equal" if not half_life else f"half-life {half_life / 365:.0f}y"


def choose_recency(rows, feats, h_equal):
    """Try each RECENCY_OPTIONS half-life on the held-back latest matches.

    Keeps the best log loss among options that beat equal weighting by the same
    rule as other additions (lower log loss, AUC no worse than -0.002).
    Returns (half_life or None, {label: holdout score}).
    """
    scores = {_hl_label(None): h_equal}
    best, best_h = None, h_equal
    print(f"  {_hl_label(None):<24} log loss {h_equal['log_loss']:.5f}  AUC {h_equal['auc']:.3f}  "
          f"predicted {100 * h_equal.get('pred', 0):.2f}% vs actual {100 * h_equal.get('actual', 0):.2f}%")
    for hl in RECENCY_OPTIONS:
        if hl is None:
            continue
        h = _holdout_score(rows, feats=feats, half_life=hl)
        scores[_hl_label(hl)] = h
        ok = h["log_loss"] < h_equal["log_loss"] - 1e-5 and h["auc"] >= h_equal["auc"] - 0.002
        print(f"  {_hl_label(hl):<24} log loss {h['log_loss']:.5f}  AUC {h['auc']:.3f}  "
              f"predicted {100 * h.get('pred', 0):.2f}% vs actual {100 * h.get('actual', 0):.2f}%"
              f"  {'(better)' if ok else ''}")
        if ok and h["log_loss"] < best_h["log_loss"]:
            best, best_h = hl, h
    print(f"  -> using {_hl_label(best)}")
    return best, scores


def choose_cal_recency(results):
    """Fit calibration on all walk-forward folds but the last, score it on the last.

    Each RECENCY_OPTIONS half-life weights the calibration towards the newest
    earlier matches; the one with the lowest log loss on the last fold is used.
    """
    from sklearn.metrics import log_loss

    if len(results) < 2:
        return None, {}
    prior_y = np.concatenate([r["y"] for r in results[:-1]])
    prior_p = np.concatenate([r["p"] for r in results[:-1]])
    prior_d = np.concatenate([r["days"] for r in results[:-1]])
    test_y, test_p = results[-1]["y"], results[-1]["p"]
    out, best, best_ll = {}, None, None
    for hl in RECENCY_OPTIONS:
        ab = platt_fit(prior_y, prior_p, recency_weights(prior_d, hl))
        pc = platt_apply(ab, test_p)
        ll = float(log_loss(test_y, np.clip(pc, 1e-6, 1 - 1e-6), labels=[0, 1]))
        out[_hl_label(hl)] = {"log_loss": ll, "pred": float(pc.mean()), "actual": float(test_y.mean())}
        print(f"  {_hl_label(hl):<24} log loss {ll:.5f}  predicted {100 * pc.mean():.2f}% "
              f"vs actual {100 * test_y.mean():.2f}%")
        if best_ll is None or ll < best_ll - 1e-6:
            best, best_ll = hl, ll
    print(f"  -> using {_hl_label(best)}")
    return best, out


def train(save=True):
    matches = load_matches()
    rows, _, _ = replay(matches)
    n_a = len(rows)
    n_b = sum(r["up2"] for r in rows)
    print(f"matches {len(matches)}  sides {n_a}  went 2-up {n_b} "
          f"({100 * n_b / max(n_a, 1):.1f}%)  failed to win once 2-up "
          f"{100 * sum(r['fail'] for r in rows) / max(n_b, 1):.1f}%")
    if n_a < MIN_ROWS_A:
        raise SystemExit(f"Only {n_a} team-sides — need {MIN_ROWS_A}. Run the historical pipeline.")

    print("\nInput sets, scored on the latest 15% of matches (never trained on):")
    h_base = _holdout_score(rows, feats=BASE_FEATURES)
    h_beh = _holdout_score(rows, feats=BASE_FEATURES + BEHAVIOUR_FEATURES)
    feats = list(BASE_FEATURES)
    holdout = h_base
    if _choose("base (V5)", h_base, "+ behaviour", h_beh):
        feats += BEHAVIOUR_FEATURES
        holdout = h_beh

    print("\nRecency weighting (recent seasons count more when fitting):")
    half_life, recency = choose_recency(rows, feats, holdout)
    holdout = recency[_hl_label(half_life)]

    ou_rows = [r for r in rows if r.get("has_ou")]
    ou = None
    print(f"\nOver/under 2.5 prices on {len(ou_rows)} of {n_a} team-sides "
          f"({100 * len(ou_rows) / max(n_a, 1):.0f}%)")
    ou_report = None
    if len(ou_rows) >= MIN_ROWS_A:
        h_c = _holdout_score(ou_rows, feats=feats, half_life=half_life)
        h_ou = _holdout_score(ou_rows, feats=feats + OU_FEATURES, half_life=half_life)
        use_ou = _choose("same games, no O/U", h_c, "+ over/under 2.5", h_ou)
        ou_report = {"without": h_c, "with": h_ou, "used": use_ou}
        if use_ou:
            ma, mb, _, _ = _fit_pair(ou_rows, feats + OU_FEATURES, half_life)
            res_o, yo, po = _walk(ou_rows, feats + OU_FEATURES, verbose=False, half_life=half_life)
            do = np.concatenate([r["days"] for r in res_o])
            ou = {"features": feats + OU_FEATURES, "model_a": ma, "model_b": mb,
                  "cal_full": platt_fit(yo, po, recency_weights(do, half_life)),
                  "rows": len(ou_rows)}
    else:
        print("  not enough games with over/under prices to test "
              "(run collectors/odds_history_fd.py)")

    model_a, model_b, ya, yb = _fit_pair(rows, feats, half_life)
    # Calibration from out-of-sample (walk-forward) predictions only.
    res_oof, y_oof, p_oof = _walk(rows, feats, verbose=False, half_life=half_life)
    print("\nCalibration weighting, tested on the latest walk-forward period:")
    cal_half_life, cal_test = choose_cal_recency(res_oof)
    d_oof = np.concatenate([r["days"] for r in res_oof])
    cal = platt_fit(y_oof, p_oof, recency_weights(d_oof, cal_half_life))
    print()
    ece_raw = _band_table(y_oof, p_oof, "Out-of-sample FTA% before calibration:")
    ece_cal = _band_table(y_oof, platt_apply(cal, p_oof), "After calibration:")

    bundle = {
        "version": VERSION,
        "features": feats,
        "model_a": model_a, "cal_a": None,
        "model_b": model_b, "cal_b": None,
        "cal_full": cal,
        "ou": ou,
        "half_life_days": HALF_LIFE_DAYS,
        "recency_half_life_days": half_life,
        "cal_half_life_days": cal_half_life,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "rows_a": int(len(ya)), "rows_b": int(len(yb)),
        "base_2up": float(ya.mean()), "base_fail": float(yb.mean()),
        "base_full": float(np.mean([r["fail"] for r in rows])),
        "holdout": holdout,
        "selection": {"base": h_base, "behaviour": h_beh,
                      "behaviour_used": feats != BASE_FEATURES, "ou": ou_report,
                      "recency": recency, "calibration_recency": cal_test},
        "calibration_gap": {"before": ece_raw, "after": ece_cal},
    }
    print(f"\nheld-out (latest 15%): full-event AUC {holdout['auc']:.3f}  "
          f"Brier {holdout['brier']:.4f}  skill vs flat rate {100 * holdout['skill']:+.1f}%")
    print(f"inputs: {len(feats)} ({'with' if feats != BASE_FEATURES else 'without'} behaviour), "
          f"recency {_hl_label(half_life)}, calibration {_hl_label(cal_half_life)}, "
          f"over/under variant {'ON' if ou else 'off'}, calibration gap "
          f"{ece_raw:.2f} -> {ece_cal:.2f} points")
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
                notes=(f"full event = P(2up) x P(fail|2up), calibrated; held-out latest 15%; "
                       f"behaviour {'on' if feats != BASE_FEATURES else 'off'}; "
                       f"O/U {'on' if ou else 'off'}; recency {_hl_label(half_life)}; "
                       f"skill vs flat {100 * holdout['skill']:+.1f}%"),
            )
        except Exception as exc:
            print(f"[path-model] could not record model run: {exc}")
    return bundle


def _holdout_score(rows, frac=0.15, feats=None, half_life=None):
    """Fit on the earliest 85% of team-sides, score the full event on the rest."""
    from sklearn.metrics import brier_score_loss, log_loss

    feats = feats or BASE_FEATURES
    rows = sorted(rows, key=lambda r: r["day"])
    cut = int(len(rows) * (1 - frac))
    train_rows, test_rows = rows[:cut], rows[cut:]
    ma, mb, _, _ = _fit_pair(train_rows, feats, half_life)
    Xt, _, sel = _xy(test_rows, "up2", feats=feats)
    p = _predict_stage(ma, None, Xt) * _predict_stage(mb, None, Xt)
    y = np.array([r["fail"] for r in sel])
    m = _metrics(y, p)
    flat = float(np.mean([r["fail"] for r in train_rows]))
    brier_flat = float(brier_score_loss(y, np.full_like(p, flat)))
    return {
        "auc": m["auc"] or 0.5, "brier": m["brier"],
        "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "skill": 1 - m["brier"] / brier_flat if brier_flat else 0.0,
        "n": int(len(y)), "pred": m["pred"], "actual": m["actual"],
    }


# --- walk-forward -----------------------------------------------------------------

FULL_BANDS = [0.0, 1.0, 2.0, 3.0, 4.0, 100.0]


def _walk(rows, feats, folds=5, min_train_frac=0.3, verbose=True, half_life=None):
    """Expanding-window walk-forward. Returns (fold results, pooled y, pooled p)."""
    from sklearn.metrics import brier_score_loss

    rows = sorted(rows, key=lambda r: r["day"])
    n = len(rows)
    start = int(n * min_train_frac)
    edges = [start + (n - start) * i // folds for i in range(folds + 1)]
    pooled_y, pooled_p, results = [], [], []
    for k in range(folds):
        train_rows, test_rows = rows[:edges[k]], rows[edges[k]:edges[k + 1]]
        ma, mb, _, _ = _fit_pair(train_rows, feats, half_life)
        Xt, _, sel = _xy(test_rows, "up2", feats=feats)
        pa = _predict_stage(ma, None, Xt)
        pb = _predict_stage(mb, None, Xt)
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
                        "skill": skill, "y": y_full, "p": full,
                        "days": np.array([r["day"] for r in sel], dtype=float)})
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


def walk_forward(folds=5, min_train_frac=0.3, feats=None):
    rows, _, _ = replay(load_matches())
    if len(rows) < MIN_ROWS_A:
        raise SystemExit(f"Only {len(rows)} team-sides — need {MIN_ROWS_A}.")
    bundle = load_bundle() or {}
    if feats is None:
        feats = bundle.get("features") or BASE_FEATURES
    half_life = bundle.get("recency_half_life_days")
    cal_half_life = bundle.get("cal_half_life_days")
    print(f"inputs: {len(feats)} ({'with' if len(feats) > len(BASE_FEATURES) else 'without'} behaviour), "
          f"fit {_hl_label(half_life)}, calibration {_hl_label(cal_half_life)}")
    results, y, p = _walk(rows, feats, folds, min_train_frac, half_life=half_life)
    print()
    _band_table(y, p, "Calibration (all test folds, raw) — predicted full-event % vs what happened")
    # Honest calibrated check: each fold is calibrated only on earlier folds.
    print()
    yc, pc = [], []
    for k in range(1, len(results)):
        prior_y = np.concatenate([r["y"] for r in results[:k]])
        prior_p = np.concatenate([r["p"] for r in results[:k]])
        prior_d = np.concatenate([r["days"] for r in results[:k]])
        ab = platt_fit(prior_y, prior_p, recency_weights(prior_d, cal_half_life))
        fold_p = platt_apply(ab, results[k]["p"])
        yc.extend(results[k]["y"])
        pc.extend(fold_p)
        print(f"fold {k + 1} calibrated: predicted {100 * fold_p.mean():.2f}% "
              f"vs actual {100 * results[k]['y'].mean():.2f}%")
    if yc:
        print()
        _band_table(np.array(yc), np.array(pc),
                    "Calibrated (folds 2+, calibration fitted on earlier folds only):")
    pred, hit, lift = _top_lift(y, p)
    print(f"\nTop 10% of picks: predicted {100 * pred:.2f}%, happened {100 * hit:.2f}% "
          f"(overall {100 * y.mean():.2f}%, lift x{lift:.2f})")
    aucs = [r["full"]["auc"] for r in results if r["full"]["auc"] is not None]
    print(f"Mean AUC (full event) {np.mean(aucs):.3f} ±{np.std(aucs):.3f}; "
          f"mean skill vs flat rate {100 * np.mean([r['skill'] for r in results]):+.1f}%")
    return results


def compare(folds=5, min_train_frac=0.3):
    """Walk-forward side by side: V5 inputs vs + behaviour (all games) and + over/under (priced games)."""
    rows, _, _ = replay(load_matches())
    ou_rows = [r for r in rows if r.get("has_ou")]

    def run(label, data, feats):
        res, y, p = _walk(data, feats, folds, min_train_frac, verbose=False)
        _, hit, lift = _top_lift(y, p)
        from sklearn.metrics import log_loss
        return label, {
            "auc_2up": float(np.mean([r["a"]["auc"] for r in res])),
            "auc_fail": float(np.mean([r["b"]["auc"] for r in res if r["b"]["auc"]])),
            "auc_full": float(np.mean([r["full"]["auc"] for r in res])),
            "lift": lift,
            "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])),
        }

    table = [run("V5 inputs", rows, BASE_FEATURES),
             run("+ behaviour", rows, BASE_FEATURES + BEHAVIOUR_FEATURES)]
    if len(ou_rows) >= MIN_ROWS_A:
        table.append(run("priced games: + behaviour", ou_rows, BASE_FEATURES + BEHAVIOUR_FEATURES))
        table.append(run("priced games: + over/under", ou_rows,
                         BASE_FEATURES + BEHAVIOUR_FEATURES + OU_FEATURES))
    print(f"team-sides {len(rows)}, with over/under prices {len(ou_rows)}")
    print(f"\n  {'inputs':<28} {'AUC 2-up':>9} {'AUC fail':>9} {'AUC full':>9} {'top10% lift':>12} {'log loss':>10}")
    for label, m in table:
        print(f"  {label:<28} {m['auc_2up']:>9.3f} {m['auc_fail']:>9.3f} {m['auc_full']:>9.3f} "
              f"{m['lift']:>11.2f}x {m['log_loss']:>10.5f}")
    print("\nLower log loss and higher AUC / lift are better. `train` keeps an addition only "
          "if it wins on the held-back matches.")
    return table


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
    for label, feats in (("without odds", BASE_FEATURES), ("with odds", BASE_FEATURES + ODDS_FEATURES)):
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


_state_lock = threading.Lock()


def state_age():
    return time.time() - _state_cache["ts"] if _state_cache["teams"] is not None else float("inf")


def _rebuild_state():
    with _state_lock:
        _, teams, leagues = replay(load_matches(), collect=False)
        _state_cache.update(ts=time.time(), teams=teams, leagues=leagues)


def current_state(force=False):
    """Team/league state for serving. Rebuilt synchronously on first use or when
    forced; once built, an expired state is served while a background thread
    rebuilds it (replaying the full history takes a while on 90k matches)."""
    if force or _state_cache["teams"] is None:
        _rebuild_state()
    elif state_age() > STATE_TTL and not _state_lock.locked():
        threading.Thread(target=_rebuild_state, daemon=True).start()
    return _state_cache["teams"], _state_cache["leagues"]


def data_confidence(t, o):
    """0–100: how much match history backs this pick (not a probability)."""
    depth = min(t.raw_n, o.raw_n)
    return round(20 + 65 * min(1.0, depth / 60.0), 1)


def prematch_features(team, opponent, league, is_home, as_of=None):
    """Point-in-time pre-match features from the live team state -> (features, t, o)."""
    teams, leagues = current_state()
    day = _day(as_of) if as_of else date.today().toordinal()
    t = teams.get(normalize_team(team)) or Decayed()
    o = teams.get(normalize_team(opponent)) or Decayed()
    lg = leagues.get(league or "") or Decayed()
    t2, o2, lg2 = _copy(t), _copy(o), _copy(lg)  # keep cached state untouched
    for s in (t2, o2, lg2):
        if s.day is not None:
            s.decay_to(day)
    return features_for(t2, o2, lg2, is_home), t, o


def predict_fixture(team, opponent, league, is_home, as_of=None, market=None):
    """None if no trained model; else the full-event breakdown in percent.

    market: optional {"over25": price, "under25": price}; used only when the
    trained bundle kept the over/under variant."""
    bundle = load_bundle()
    if bundle is None:
        return None
    f, t, o = prematch_features(team, opponent, league, is_home, as_of)
    variant = bundle
    ou_variant = bundle.get("ou")
    if ou_variant and market:
        f.update(_ou_features((market.get("over25"), market.get("under25"))))
        if f.get("has_ou"):
            variant = ou_variant
    X = np.array([[f[k] for k in variant["features"]]], dtype=float)
    pa = float(_predict_stage(variant["model_a"], variant.get("cal_a"), X)[0])
    pb = float(_predict_stage(variant["model_b"], variant.get("cal_b"), X)[0])
    full = pa * pb
    cal = variant.get("cal_full")
    if cal:
        full = float(platt_apply(cal, np.array([full]))[0])
    # keep the displayed breakdown consistent: two_up x fail = FTA
    pb_shown = min(full / pa, 0.99) if pa > 0 else pb
    return {
        "two_up_pct": round(100 * pa, 2),
        "fail_given_2up_pct": round(100 * pb_shown, 2),
        "fta_pct": round(100 * full, 2),
        "usual_2up_minute": round(f["t_2up_minute"], 1),
        "data_confidence": data_confidence(t, o),
        "model_version": bundle["version"] + ("+ou" if variant is ou_variant else ""),
        "calibrated": bool(cal),
    }


def _copy(s):
    c = Decayed()
    c.day, c.raw_n = s.day, s.raw_n
    for k in TEAM_KEYS:
        setattr(c, k, getattr(s, k))
    return c


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["train", "walk-forward", "odds-test", "compare"])
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args(argv)
    if args.command == "train":
        train()
    elif args.command == "odds-test":
        odds_test(folds=args.folds)
    elif args.command == "compare":
        compare(folds=args.folds)
    else:
        walk_forward(folds=args.folds)


if __name__ == "__main__":
    main()
