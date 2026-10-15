"""
Goal Likelihood (trial): how likely a game is to have goals, separate from the
Chaos number. Three chances per game, built only from matches before it:

  BTTS        both teams score
  Over 2.5    3+ goals
  Early goal  a goal by minute 30 (same cutoff as the results collector)

Each team keeps decayed scoring / conceding rates (pulled towards its league
when it has few games). Expected goals per side = league average x attack x
opponent's defence (+ league home edge), then Poisson gives the three chances,
and a calibration fitted on recent seasons corrects them. The Goal score is
0.4 BTTS + 0.4 Over 2.5 + 0.2 early goal, on 0-100.

    venv/bin/python -u models/goal_likelihood.py check   # backtest vs the Chaos-style average
"""

from __future__ import annotations

import math
import sys
import threading
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EARLY_CUTOFF = 30
HALF_LIFE_DAYS = 240.0
PRIOR_GAMES = 6.0          # a team's rates lean on its league until it has this many (decayed) games
WEIGHTS = {"btts": 0.4, "over25": 0.4, "early": 0.2}
TARGETS = ("btts", "over25", "early", "btts_over25")
CALIBRATION_YEARS = 3      # serving calibration is fitted on the most recent seasons
STATE_TTL = 3600


def _early(m):
    goals = m.get("goals")
    if goals is not None:
        return int(any((g[0] or 0) <= EARLY_CUTOFF for g in goals))
    sides = m.get("sides") or {}
    flags = [(sides.get(k) or {}).get("early_for") for k in (1, 2)]
    if any(f is None for f in flags):
        return None
    return int(any(flags))


def outcomes(m):
    fh, fa = m["fh"], m["fa"]
    return {"btts": int(fh > 0 and fa > 0), "over25": int(fh + fa >= 3), "early": _early(m),
            "btts_over25": int(fh > 0 and fa > 0 and fh + fa >= 3)}


class _Acc:
    """Decayed sums (one per key), all decayed to the same day."""
    __slots__ = ("day", "v")

    def __init__(self):
        self.day = None
        self.v = defaultdict(float)

    def to(self, day):
        if self.day is not None and day > self.day:
            f = 0.5 ** ((day - self.day) / HALF_LIFE_DAYS)
            for k in self.v:
                self.v[k] *= f
        if self.day is None or day > self.day:
            self.day = day
        return self


class State:
    def __init__(self):
        self.teams = defaultdict(_Acc)
        self.leagues = defaultdict(_Acc)

    def _league(self, league, day):
        lg = self.leagues[league].to(day).v
        n = lg["n"]
        if n < 5:   # brand-new league: generic football numbers
            return {"home": 1.45, "away": 1.15, "early_share": 0.30, "n": n}
        return {"home": lg["hg"] / n, "away": lg["ag"] / n,
                "early_share": (lg["early_goals"] / lg["goals"]) if lg["goals"] else 0.30, "n": n}

    def _team(self, team, day, league_avg):
        t = self.teams[team].to(day).v
        n = t["n"]
        att = (t["gf"] + PRIOR_GAMES * league_avg) / (n + PRIOR_GAMES) / league_avg
        dfn = (t["ga"] + PRIOR_GAMES * league_avg) / (n + PRIOR_GAMES) / league_avg
        rate = lambda k: (t[k] / n) if n else None  # noqa: E731  plain team rates (Chaos-style)
        return {"att": att, "def": dfn, "n": n, "btts": rate("btts"), "over25": rate("over25"),
                "early": rate("early")}

    def predict(self, home, away, league, day):
        lg = self._league(league, day)
        avg = (lg["home"] + lg["away"]) / 2 or 1.3
        h, a = self._team(home, day, avg), self._team(away, day, avg)
        lam_h = max(0.05, lg["home"] * h["att"] * a["def"])
        lam_a = max(0.05, lg["away"] * a["att"] * h["def"])
        p = poisson_chances(lam_h, lam_a, lg["early_share"])
        naive = {k: (h[k] + a[k]) / 2 if h[k] is not None and a[k] is not None else None
                 for k in ("btts", "over25", "early")}
        return {"raw": p, "naive": naive, "xg_home": lam_h, "xg_away": lam_a,
                "games": (h["n"], a["n"])}

    def update(self, m):
        day, o = m["day"], outcomes(m)
        lg = self.leagues[m["league"]].to(day).v
        lg["n"] += 1
        lg["hg"] += m["fh"]
        lg["ag"] += m["fa"]
        goals = m.get("goals")
        if goals is not None:
            lg["goals"] += len(goals)
            lg["early_goals"] += sum(1 for g in goals if (g[0] or 0) <= EARLY_CUTOFF)
        for team, gf, ga in ((m["home"], m["fh"], m["fa"]), (m["away"], m["fa"], m["fh"])):
            t = self.teams[team].to(day).v
            t["n"] += 1
            t["gf"] += gf
            t["ga"] += ga
            t["btts"] += o["btts"]
            t["over25"] += o["over25"]
            if o["early"] is not None:
                t["early"] += o["early"]
            else:   # unknown: count it at the team's own rate so the average isn't dragged down
                t["early"] += (t["early"] / max(t["n"] - 1, 1)) if t["n"] > 1 else 0.5


def poisson_chances(lam_h, lam_a, early_share):
    ph = [math.exp(-lam_h) * lam_h ** k / math.factorial(k) for k in range(3)]
    pa = [math.exp(-lam_a) * lam_a ** k / math.factorial(k) for k in range(3)]
    btts = (1 - ph[0]) * (1 - pa[0])
    under = sum(ph[i] * pa[j] for i in range(3) for j in range(3) if i + j <= 2)
    # BTTS and 3+: everything with both >= 1, minus 1-1
    btts_over = btts - ph[1] * pa[1]
    early = 1 - math.exp(-(lam_h + lam_a) * early_share)
    return {"btts": btts, "over25": 1 - under, "early": early, "btts_over25": max(btts_over, 0.0)}


# --- lay the draw: what a first goal would do to the draw price ---------------

LTD_EXIT = 60          # still 0-0 at this minute: trade out for a loss
LTD_GOOD_GREEN = 1.0   # a first goal "pays" if it locks in at least this per £10 laid


def _pois_vec(lam, n=12):
    k = np.arange(n)
    fact = np.array([math.factorial(int(i)) for i in k], float)
    return np.exp(-lam) * lam ** k / fact


def draw_chance(lam_h, lam_a, lead=0):
    """P(final draw) with lam_* goals still to come and the home side `lead` goals up."""
    ph, pa = _pois_vec(lam_h), _pois_vec(lam_a)
    return float(sum(ph[j - lead] * pa[j] for j in range(len(pa)) if 0 <= j - lead < len(ph)))


def ltd_profile(lam_h, lam_a, lay=None, exit_minute=LTD_EXIT, stake=10.0):
    """
    For laying the draw before kick-off and trading out after the first goal:
    where the draw price goes if each side scores first, and how often a first goal
    before `exit_minute` is worth trading (locks in >= LTD_GOOD_GREEN per £10).
    Fair prices from the expected goals; real prices carry a spread.
    """
    tot = lam_h + lam_a
    lay = lay or 1 / max(draw_chance(lam_h, lam_a), 1e-6)
    fav_home = lam_h >= lam_a

    def after(minute, lead):
        r = max(0.0, (90 - minute) / 90)
        back = 1 / max(draw_chance(lam_h * r, lam_a * r, lead), 1e-6)
        return back, stake - stake * lay / back

    good = exp_green = p_goal = 0.0
    for t in range(1, exit_minute + 1):       # first goal in minute t
        dens = math.exp(-tot * (t - 1) / 90) - math.exp(-tot * t / 90)
        for lam, lead in ((lam_h, 1), (lam_a, -1)):
            w = dens * lam / tot
            _, g = after(t, lead)
            p_goal += w
            exp_green += w * g
            if g >= LTD_GOOD_GREEN:
                good += w
    fav_b, fav_g = after(30, 1 if fav_home else -1)
    dog_b, dog_g = after(30, -1 if fav_home else 1)
    nil_b, nil_g = after(exit_minute, 0)
    return {
        "lay": round(lay, 2),
        "goal_before_exit_pct": round(100 * p_goal, 1),
        "good_goal_pct": round(100 * good, 1),
        "fav_first_pct": round(100 * max(lam_h, lam_a) / tot, 1),
        "fav_scores": {"draw": round(fav_b, 2), "green": round(fav_g, 2)},
        "dog_scores": {"draw": round(dog_b, 2), "green": round(dog_g, 2)},
        "nil_at_exit": {"draw": round(nil_b, 2), "green": round(nil_g, 2), "pct": round(100 * math.exp(-tot * exit_minute / 90), 1)},
        "avg_green_after_goal": round(exp_green / p_goal, 2) if p_goal else None,
        "exit_minute": exit_minute,
    }


# --- calibration ---------------------------------------------------------------

def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_platt(p, y, iters=50):
    """logit(p_cal) = a + b logit(p); Newton steps, lightly ridged."""
    x, y = _logit(p), np.asarray(y, float)
    a, b = 0.0, 1.0
    for _ in range(iters):
        z = a + b * x
        q = 1 / (1 + np.exp(-z))
        w = q * (1 - q)
        g = np.array([np.sum(q - y), np.sum((q - y) * x) + 1e-3 * (b - 1)])
        H = np.array([[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x) + 1e-3]]) + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        a, b = a - step[0], b - step[1]
        if np.abs(step).max() < 1e-7:
            break
    return {"a": float(a), "b": float(b)}


def apply_platt(p, cal):
    if not cal:
        return float(p)
    return float(1 / (1 + math.exp(-(cal["a"] + cal["b"] * float(_logit(p))))))


# --- history walk --------------------------------------------------------------

def walk(matches):
    """Point-in-time predictions for every match (predict, then learn from it)."""
    st, rows = State(), []
    for m in matches:
        pred = st.predict(m["home"], m["away"], m["league"], m["day"])
        rows.append((m, pred, outcomes(m)))
        st.update(m)
    return st, rows


def _usable(rows, min_games=3):
    return [r for r in rows if min(r[1]["games"]) >= min_games]


def fit_calibration(rows):
    cal = {}
    for k in TARGETS:
        sel = [(r[1]["raw"][k], r[2][k]) for r in rows if r[2][k] is not None]
        if len(sel) >= 500:
            p, y = zip(*sel)
            cal[k] = fit_platt(p, y)
    return cal


def calibrated(raw, cal):
    out = {k: apply_platt(raw[k], cal.get(k)) for k in TARGETS}
    out["btts_over25"] = min(out["btts_over25"], out["btts"], out["over25"])
    return out


def goal_score(p):
    return 100.0 * sum(w * p[k] for k, w in WEIGHTS.items())


# --- serving -------------------------------------------------------------------

_state = {"ts": 0.0, "st": None, "cal": None, "n": 0}
_lock = threading.Lock()


def _build():
    from models.fta_path_model import load_matches

    matches = load_matches()
    st, rows = walk(matches)
    last = matches[-1]["day"] if matches else 0
    recent = [r for r in _usable(rows) if r[0]["day"] >= last - 365 * CALIBRATION_YEARS]
    return st, fit_calibration(recent), len(matches)


def current(force=False):
    """(state, calibration), rebuilt at most hourly; one build at a time."""
    if _state["st"] is not None and not force and time.time() - _state["ts"] < STATE_TTL:
        return _state["st"], _state["cal"]
    with _lock:
        if _state["st"] is None or force or time.time() - _state["ts"] >= STATE_TTL:
            st, cal, n = _build()
            _state.update(ts=time.time(), st=st, cal=cal, n=n)
    return _state["st"], _state["cal"]


def _today():
    return date.today().toordinal()


def match_goals(home, away, league="", kickoff=None, match_id=None, state=None):
    from team_normalizer import normalize_team

    st, cal = state or current()
    h, a = normalize_team(home), normalize_team(away)
    pred = st.predict(h, a, league or "", _today())
    p = calibrated(pred["raw"], cal)
    g_home, g_away = pred["games"]
    return {
        "match_id": match_id, "match": f"{home} vs {away}", "league": league or "", "kickoff": kickoff,
        "home_team": home, "away_team": away,
        "goal_score": round(goal_score(p), 1),
        "btts_pct": round(100 * p["btts"], 1),
        "over25_pct": round(100 * p["over25"], 1),
        "early_goal_pct": round(100 * p["early"], 1),
        "btts_over25_pct": round(100 * p["btts_over25"], 1),
        "xg_home": round(pred["xg_home"], 2), "xg_away": round(pred["xg_away"], 2),
        "thin_data": min(g_home, g_away) < 5,
        "ltd": ltd_profile(pred["xg_home"], pred["xg_away"]),
        "feature": "goal_likelihood",
    }


def rank_goal_matches(fixtures):
    state = current()
    seen, out = set(), []
    for fx in fixtures:
        home, away = fx.get("home_team"), fx.get("away_team")
        key = (home, away, fx.get("kickoff") or fx.get("match_id"))
        if not home or not away or key in seen:
            continue
        seen.add(key)
        out.append(match_goals(home, away, fx.get("league") or "", fx.get("kickoff"), fx.get("match_id"), state))
    out.sort(key=lambda r: r["goal_score"], reverse=True)
    return out


# --- backtest ------------------------------------------------------------------

def _logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _auc(s, y):
    s, y = np.asarray(s, float), np.asarray(y, int)
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def backtest(matches, test_years=2):
    """Calibrate on everything before the last `test_years`, score those years.
    Compares with the Chaos-style average of the two teams' own rates."""
    _, rows = walk(matches)
    rows = _usable(rows)
    if not rows:
        return None
    split = rows[-1][0]["day"] - 365 * test_years
    train = [r for r in rows if r[0]["day"] < split]
    test = [r for r in rows if r[0]["day"] >= split]
    cal = fit_calibration(train)
    res = {"train": len(train), "test": len(test), "targets": {}, "top": {}}
    preds = [calibrated(r[1]["raw"], cal) for r in test]
    for k in TARGETS:
        idx = [i for i, r in enumerate(test) if r[2][k] is not None]
        y = [test[i][2][k] for i in idx]
        p = [preds[i][k] for i in idx]
        base = float(np.mean([r[2][k] for r in train if r[2][k] is not None]))
        row = {"n": len(y), "actual": float(np.mean(y)), "predicted": float(np.mean(p)),
               "logloss": _logloss(p, y), "logloss_base": _logloss([base] * len(y), y), "auc": _auc(p, y)}
        if k != "btts_over25":
            nv = [(test[i][1]["naive"][k], test[i][2][k]) for i in idx if test[i][1]["naive"][k] is not None]
            if nv:
                row["auc_naive"] = _auc([a for a, _ in nv], [b for _, b in nv])
        res["targets"][k] = row
    # the filter question: of the top 20% of games by each score, how many delivered?
    goal = np.array([goal_score(p) for p in preds])
    naive_ok = [i for i, r in enumerate(test) if all(r[1]["naive"][k] is not None for k in WEIGHTS)]
    naive = {i: sum(w * test[i][1]["naive"][k] for k, w in WEIGHTS.items()) for i in naive_ok}
    for name, scores in (("goal score", {i: goal[i] for i in naive_ok}), ("chaos-style average", naive)):
        ids = sorted(scores, key=lambda i: -scores[i])[: max(1, len(scores) // 5)]
        res["top"][name] = {k: float(np.mean([test[i][2][k] for i in ids if test[i][2][k] is not None]))
                            for k in TARGETS}
    res["top"]["all games"] = {k: float(np.mean([test[i][2][k] for i in naive_ok if test[i][2][k] is not None]))
                               for k in TARGETS}
    bands = []
    for lo, hi in ((0, 40), (40, 50), (50, 60), (60, 70), (70, 101)):
        ids = [i for i in range(len(test)) if lo <= goal[i] < hi]
        if ids:
            bands.append({"band": f"{lo}-{hi if hi < 101 else 100}", "n": len(ids),
                          **{k: float(np.mean([test[i][2][k] for i in ids if test[i][2][k] is not None] or [np.nan]))
                             for k in TARGETS}})
    res["bands"] = bands
    return res


def check():
    from models.fta_path_model import load_matches

    t = time.time()
    res = backtest(load_matches())
    if not res:
        print("no matches")
        return
    print(f"Goal Likelihood backtest: calibrated on {res['train']} games, tested on {res['test']} (last 2 seasons)")
    names = {"btts": "BTTS", "over25": "Over 2.5", "early": "Goal by 30'", "btts_over25": "BTTS & O2.5"}
    print("  target       |     n | actual | predicted | log loss (base) | AUC  | AUC chaos-style")
    for k, r in res["targets"].items():
        print(f"  {names[k]:<12} | {r['n']:>5} | {100 * r['actual']:5.1f}% | {100 * r['predicted']:8.1f}% | "
              f"{r['logloss']:.4f} ({r['logloss_base']:.4f}) | {r['auc']:.3f} | "
              f"{r.get('auc_naive', float('nan')):.3f}")
    print("  Top 20% of games by each score (what actually happened):")
    for name, r in res["top"].items():
        print(f"    {name:<20} " + "  ".join(f"{names[k]} {100 * v:4.1f}%" for k, v in r.items()))
    print("  By goal score band:")
    for b in res["bands"]:
        print(f"    {b['band']:<7} n={b['n']:>5}  " + "  ".join(f"{names[k]} {100 * b[k]:4.1f}%" for k in TARGETS))
    print(f"  ({time.time() - t:.0f}s) AUC 0.5 = no better than chance; higher than chaos-style = sharper filter.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check()
    else:
        print(__doc__)
