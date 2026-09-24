#!/usr/bin/env python3
"""
Sweep Chaos v1 score bands × min O2.5 odds for any positive flat-stake ROI.

Uses same CSV form features as v1. Reports only slices with enough trades.

Usage:
  python3 -u scripts/backtest_chaos_pnl_bands.py --dir data/football_data
  python3 -u scripts/backtest_chaos_pnl_bands.py --dir data/football_data --min-trades 100
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


def _o25_odds(row):
    odds = _f(row, "B365>2.5", "P>2.5", "PS>2.5", "Avg>2.5", "BbAv>2.5", "Max>2.5", "B365C>2.5")
    if odds and 1.01 < odds < 10:
        return odds
    for k, v in row.items():
        if v and ">2.5" in k:
            try:
                c = float(str(v).strip())
                if 1.01 < c < 10:
                    return c
            except ValueError:
                pass
    return None


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
        hth, hta = _i(row, "HTHG"), _i(row, "HTAG")
        goals = fth + fta
        out.append(
            {
                "date": (row.get("Date") or "").strip(),
                "home": home,
                "away": away,
                "fth": fth,
                "fta": fta,
                "o25": int(goals >= 3),
                "o25_odds": _o25_odds(row),
                "btts": int(fth > 0 and fta > 0),
                "fh_goal": int((hth + hta) > 0) if hth is not None and hta is not None else None,
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
        return {"n": 0, "btts": 50.0, "o25": 50.0, "early": 50.0, "gf": 1.2, "ga": 1.2}
    return {
        "n": n,
        "btts": 100.0 * sum(h["btts"] for h in history) / n,
        "o25": 100.0 * sum(h["o25"] for h in history) / n,
        "early": (
            100.0
            * sum(h["fh"] for h in history if h.get("fh") is not None)
            / max(1, sum(1 for h in history if h.get("fh") is not None))
            if any(h.get("fh") is not None for h in history)
            else 50.0
        ),
        "gf": sum(h["gf"] for h in history) / n,
        "ga": sum(h["ga"] for h in history) / n,
    }


def chaos_v1(h, a):
    o2 = (h["o25"] + a["o25"]) / 2
    bt = (h["btts"] + a["btts"]) / 2
    early = (h["early"] + a["early"]) / 2
    vol = min(100.0, ((h["gf"] + h["ga"] + a["gf"] + a["ga"]) / 2) * 12.5)
    return 0.28 * o2 + 0.28 * bt + 0.22 * early + 0.22 * vol


def build(matches, form_n=8):
    hist = defaultdict(lambda: deque(maxlen=form_n))
    rows = []
    for m in matches:
        h, a = form_side(hist[m["home"]]), form_side(hist[m["away"]])
        if h["n"] < max(3, form_n // 3) or a["n"] < max(3, form_n // 3):
            hist[m["home"]].append(
                {"gf": m["fth"], "ga": m["fta"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
            )
            hist[m["away"]].append(
                {"gf": m["fta"], "ga": m["fth"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
            )
            continue
        score = chaos_v1(h, a)
        rows.append(
            {
                "chaos": round(score, 2),
                "o25": m["o25"],
                "o25_odds": m["o25_odds"],
            }
        )
        hist[m["home"]].append(
            {"gf": m["fth"], "ga": m["fta"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
        )
        hist[m["away"]].append(
            {"gf": m["fta"], "ga": m["fth"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
        )
    return rows


def pnl(rows, stake=10.0):
    trades = [r for r in rows if r.get("o25_odds") and r["o25_odds"] > 1.01]
    if not trades:
        return None
    profit = sum(
        stake * (r["o25_odds"] - 1.0) if r["o25"] else -stake for r in trades
    )
    staked = stake * len(trades)
    wins = sum(1 for r in trades if r["o25"])
    avg_odds = sum(r["o25_odds"] for r in trades) / len(trades)
    return {
        "trades": len(trades),
        "wins": wins,
        "hit_rate": round(100.0 * wins / len(trades), 1),
        "avg_odds": round(avg_odds, 3),
        "profit": round(profit, 2),
        "roi_pct": round(100.0 * profit / staked, 2),
        "staked": round(staked, 2),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    p.add_argument("--stake", type=float, default=10.0)
    p.add_argument("--min-trades", type=int, default=80)
    p.add_argument("--form", type=int, default=8)
    args = p.parse_args()

    files = sorted(Path(args.dir).glob("*.csv"))
    matches = []
    for f in files:
        matches.extend(parse_rows(f))
    matches.sort(key=lambda m: (_date_key(m["date"]), m["home"]))
    rows = build(matches, args.form)
    print(f"scored: {len(rows)}")

    # Fixed bands
    bands = [
        ("all", 0, 101),
        ("micro_0_40", 0, 40),
        ("low_40_55", 40, 55),
        ("mid_55_70", 55, 70),
        ("high_70_80", 70, 80),
        ("elite_80_90", 80, 90),
        ("ultra_90_plus", 90, 101),
        ("high_70_plus", 70, 101),
        ("elite_80_plus", 80, 101),
    ]

    odds_floors = [0, 1.50, 1.60, 1.70, 1.80, 1.90, 2.00]

    grid = []
    positives = []

    for bname, lo, hi in bands:
        band_rows = [r for r in rows if lo <= r["chaos"] < hi]
        for floor in odds_floors:
            subset = [
                r
                for r in band_rows
                if r.get("o25_odds") and r["o25_odds"] >= floor
            ]
            stats = pnl(subset, args.stake)
            if not stats or stats["trades"] < args.min_trades:
                continue
            entry = {
                "band": bname,
                "chaos_lo": lo,
                "chaos_hi": hi,
                "min_odds": floor,
                **stats,
            }
            grid.append(entry)
            if stats["roi_pct"] is not None and stats["roi_pct"] > 0:
                positives.append(entry)

    # Decile sweep (equal count)
    ranked = sorted(rows, key=lambda r: r["chaos"])
    chunk = max(1, len(ranked) // 10)
    decile_grid = []
    for i in range(10):
        part = ranked[i * chunk : (i + 1) * chunk] if i < 9 else ranked[i * chunk :]
        for floor in (0, 1.70, 1.85):
            subset = [r for r in part if r.get("o25_odds") and r["o25_odds"] >= floor]
            stats = pnl(subset, args.stake)
            if not stats or stats["trades"] < max(40, args.min_trades // 2):
                continue
            entry = {
                "decile": i + 1,
                "score_lo": round(min(r["chaos"] for r in part), 1),
                "score_hi": round(max(r["chaos"] for r in part), 1),
                "min_odds": floor,
                **stats,
            }
            decile_grid.append(entry)
            if stats["roi_pct"] > 0:
                positives.append({**entry, "band": f"decile_{i+1}"})

    # Sort positives by ROI desc
    positives.sort(key=lambda x: x["roi_pct"], reverse=True)
    # Best overall (least negative if no positives)
    grid_sorted = sorted(grid, key=lambda x: x["roi_pct"], reverse=True)

    out = {
        "n_scored": len(rows),
        "min_trades": args.min_trades,
        "positive_roi_slices": positives[:20],
        "positive_count": len(positives),
        "top_10_roi_any": grid_sorted[:10],
        "bottom_5_roi": grid_sorted[-5:] if grid_sorted else [],
        "decile_sample": decile_grid,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
