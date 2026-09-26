#!/usr/bin/env python3
"""
Mismatch Meter walk-forward backtest on football-data CSVs.

Ranks matches by strength mismatch (form-based underdog quality).
Reports underdog win / double-chance hit rates by score band,
and flat-stake P/L on underdog 1X2 when odds exist.

Usage:
  python3 -u scripts/backtest_mismatch_meter.py --dir data/football_data
  python3 -u scripts/backtest_mismatch_meter.py --dir data/football_data --min-score 60 --stake 10
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _f(row, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            try:
                return float(str(row[k]).strip())
            except ValueError:
                continue
    return None


def _i(row, *keys):
    v = _f(row, *keys)
    return int(v) if v is not None else None


def parse_rows(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        if not home or not away:
            continue
        fth, fta = _i(row, "FTHG", "HG"), _i(row, "FTAG", "AG")
        if fth is None or fta is None:
            continue
        home_odds = _f(row, "B365H", "PSH", "AvgH", "BbAvH", "BWH", "IWH")
        away_odds = _f(row, "B365A", "PSA", "AvgA", "BbAvA", "BWA", "IWA")
        draw_odds = _f(row, "B365D", "PSD", "AvgD", "BbAvD")
        out.append(
            {
                "date": (row.get("Date") or "").strip(),
                "home": home,
                "away": away,
                "fth": fth,
                "fta": fta,
                "home_win": int(fth > fta),
                "away_win": int(fta > fth),
                "draw": int(fth == fta),
                "home_odds": home_odds,
                "away_odds": away_odds,
                "draw_odds": draw_odds,
            }
        )
    return out


def _date_key(s):
    parts = s.replace("-", "/").split("/")
    if len(parts) != 3:
        return (9999, 99, 99)
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        if y < 100:
            y += 2000 if y < 70 else 1900
        return (y, m, d)
    except ValueError:
        return (9999, 99, 99)


def form_side(history):
    n = len(history)
    if n == 0:
        return {"n": 0, "gf": 1.2, "ga": 1.2, "pts": 1.0, "gd": 0.0}
    gf = sum(h["gf"] for h in history) / n
    ga = sum(h["ga"] for h in history) / n
    pts = sum(h["pts"] for h in history) / n
    return {"n": n, "gf": gf, "ga": ga, "pts": pts, "gd": gf - ga}


def strength(side, home_bump=0.0):
    """0–100-ish strength from rolling form."""
    attack = min(100.0, (side["gf"] / 2.2) * 100.0)
    defence = max(0.0, 100.0 - (side["ga"] / 2.2) * 100.0)
    form = min(100.0, max(0.0, 50.0 + side["gd"] * 20.0 + (side["pts"] - 1.0) * 15.0))
    return 0.35 * attack + 0.35 * defence + 0.30 * form + home_bump


def mismatch_score(h, a, home_odds, away_odds):
    hs = strength(h, home_bump=3.0)
    as_ = strength(a, home_bump=0.0)

    # Market underdog from odds if both present else weaker model side
    if home_odds and away_odds and home_odds > 1.01 and away_odds > 1.01:
        dog_is_home = home_odds > away_odds
    else:
        dog_is_home = hs < as_

    dog_s = hs if dog_is_home else as_
    fav_s = as_ if dog_is_home else hs
    quality_gap = dog_s - fav_s  # often negative

    raw = 50.0 + quality_gap * 1.8
    if home_odds and away_odds:
        # market gap vs model gap
        fav_odds = away_odds if dog_is_home else home_odds
        dog_odds = home_odds if dog_is_home else away_odds
        try:
            fav_imp = 1.0 / float(fav_odds)
            dog_imp = 1.0 / float(dog_odds)
            market_gap = fav_imp - dog_imp
            model_gap = (fav_s - dog_s) / 100.0
            raw += max(0.0, (market_gap - model_gap) * 40.0)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    score = max(0.0, min(100.0, raw))
    dog_odds = (home_odds if dog_is_home else away_odds) if home_odds and away_odds else None
    return {
        "score": round(score, 2),
        "dog_is_home": dog_is_home,
        "dog_strength": round(dog_s, 1),
        "fav_strength": round(fav_s, 1),
        "dog_odds": dog_odds,
    }


def push(hist, m):
    # home perspective
    if m["home_win"]:
        hp, ap = 3, 0
    elif m["away_win"]:
        hp, ap = 0, 3
    else:
        hp = ap = 1
    hist[m["home"]].append({"gf": m["fth"], "ga": m["fta"], "pts": hp})
    hist[m["away"]].append({"gf": m["fta"], "ga": m["fth"], "pts": ap})


def band(score):
    if score >= 70:
        return "high_70plus"
    if score >= 55:
        return "mid_55_70"
    if score >= 40:
        return "low_40_55"
    return "micro_under_40"


def run(matches, form_n=8):
    hist = defaultdict(lambda: deque(maxlen=form_n))
    rows = []
    for m in matches:
        h, a = form_side(hist[m["home"]]), form_side(hist[m["away"]])
        if h["n"] < max(3, form_n // 3) or a["n"] < max(3, form_n // 3):
            push(hist, m)
            continue
        mm = mismatch_score(h, a, m["home_odds"], m["away_odds"])
        dog_win = m["home_win"] if mm["dog_is_home"] else m["away_win"]
        dog_dc = dog_win or m["draw"]  # double chance
        rows.append(
            {
                "score": mm["score"],
                "dog_win": int(dog_win),
                "dog_dc": int(dog_dc),
                "draw": m["draw"],
                "dog_odds": mm["dog_odds"],
                "dog_is_home": mm["dog_is_home"],
            }
        )
        push(hist, m)
    return rows


def _rate(hits, n):
    return round(100.0 * hits / n, 1) if n else None


def slice_stats(rows, stake=10.0):
    n = len(rows)
    if not n:
        return {"n": 0}
    wins = sum(r["dog_win"] for r in rows)
    dcs = sum(r["dog_dc"] for r in rows)
    draws = sum(r["draw"] for r in rows)

    # P/L underdog ML
    trades = [r for r in rows if r.get("dog_odds") and r["dog_odds"] > 1.01]
    pnl = None
    if trades:
        profit = sum(
            stake * (r["dog_odds"] - 1.0) if r["dog_win"] else -stake for r in trades
        )
        staked = stake * len(trades)
        pnl = {
            "trades": len(trades),
            "wins": sum(r["dog_win"] for r in trades),
            "hit_rate": _rate(sum(r["dog_win"] for r in trades), len(trades)),
            "avg_odds": round(sum(r["dog_odds"] for r in trades) / len(trades), 3),
            "profit": round(profit, 2),
            "staked": round(staked, 2),
            "roi_pct": round(100.0 * profit / staked, 2),
        }

    return {
        "n": n,
        "dog_win_pct": _rate(wins, n),
        "dog_dc_pct": _rate(dcs, n),
        "draw_pct": _rate(draws, n),
        "dog_ml_pnl": pnl,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    ap.add_argument("--form", type=int, default=8)
    ap.add_argument("--min-score", type=float, default=60.0)
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--top-pct", type=float, default=None)
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.csv"))
    if not files:
        print(f"No CSVs in {args.dir}")
        sys.exit(1)

    matches = []
    for f in files:
        matches.extend(parse_rows(f))
    matches.sort(key=lambda m: (_date_key(m["date"]), m["home"]))
    print(f"matches loaded: {len(matches)}")

    rows = run(matches, args.form)
    print(f"matches scored: {len(rows)}")

    baseline = slice_stats(rows, args.stake)

    by_band = {}
    for bname in ("high_70plus", "mid_55_70", "low_40_55", "micro_under_40"):
        sub = [r for r in rows if band(r["score"]) == bname]
        st = slice_stats(sub, args.stake)
        if baseline.get("dog_win_pct") is not None and st.get("dog_win_pct") is not None:
            st["lift_dog_win_pp"] = round(st["dog_win_pct"] - baseline["dog_win_pct"], 1)
            st["lift_dog_dc_pp"] = round(st["dog_dc_pct"] - baseline["dog_dc_pct"], 1)
        by_band[bname] = st

    if args.top_pct is not None:
        n_top = max(1, int(len(rows) * args.top_pct / 100.0))
        selected = sorted(rows, key=lambda r: r["score"], reverse=True)[:n_top]
        mode = f"top_{args.top_pct}pct"
    else:
        selected = [r for r in rows if r["score"] >= args.min_score]
        mode = f"min_{args.min_score}"

    sel = slice_stats(selected, args.stake)
    if baseline.get("dog_win_pct") is not None and sel.get("dog_win_pct") is not None:
        sel["lift_dog_win_pp"] = round(sel["dog_win_pct"] - baseline["dog_win_pct"], 1)
        sel["lift_dog_dc_pp"] = round(sel["dog_dc_pct"] - baseline["dog_dc_pct"], 1)

    out = {
        "select_mode": mode,
        "baseline": baseline,
        "selected": sel,
        "by_band": by_band,
        "note": (
            "dog_win = underdog full-time win; dog_dc = win or draw. "
            "P/L is flat stake on underdog 1X2 when odds present."
        ),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
