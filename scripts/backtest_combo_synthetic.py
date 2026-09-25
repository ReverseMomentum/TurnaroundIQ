#!/usr/bin/env python3
"""
Synthetic combo backtest: settle BTTS AND O2.5, price ≈ O2.5_odds × BTTS_odds.

IMPORTANT
  - Combo price is SYNTHETIC (product of two markets). Real books price a
    correlated combo tighter, so ROI here is OPTIMISTIC.
  - O2.5 odds from standard football-data columns (known good).
  - BTTS odds ONLY from explicit BTTS Yes column names (no fuzzy / 1X2 fallback).

Usage:
  python3 -u scripts/backtest_combo_synthetic.py --dir data/football_data
  python3 -u scripts/backtest_combo_synthetic.py --dir data/football_data --min-trades 50
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

# Strict BTTS Yes names only — do NOT include 1X2 / AH / random matches
BTTS_YES_KEYS = (
    "B365BTTS",
    "B365BTTSY",
    "BTTSY",
    "BTTSYes",
    "BTTS_Y",
    "BbAvBTTS",
    "AvgBTTS",
    "PSBTTS",
    "PCBTTS",
    "MaxBTTS",
)

O25_KEYS = (
    "B365>2.5",
    "P>2.5",
    "PS>2.5",
    "Avg>2.5",
    "BbAv>2.5",
    "Max>2.5",
    "B365C>2.5",
)


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
    odds = _f(row, *O25_KEYS)
    if odds and 1.01 < odds < 8:
        return odds
    for k, v in row.items():
        if v and ">2.5" in k and "<" not in k:
            try:
                c = float(str(v).strip())
                if 1.01 < c < 8:
                    return c
            except ValueError:
                pass
    return None


def _btts_odds(row):
    odds = _f(row, *BTTS_YES_KEYS)
    if odds and 1.01 < odds < 6:
        return odds
    # strict: key must contain 'btts' and look like Yes (not No / N)
    for k, v in row.items():
        if not v:
            continue
        kl = k.lower().replace(" ", "")
        if "btts" not in kl:
            continue
        if kl.endswith("n") or "bttsn" in kl or "bttsno" in kl or "btts_n" in kl:
            continue
        if not ("y" in kl or kl.endswith("btts") or "yes" in kl or "avbtts" in kl):
            continue
        try:
            c = float(str(v).strip())
            if 1.20 < c < 5.5:  # realistic BTTS Yes band
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
        btts = int(fth > 0 and fta > 0)
        o25 = int(fth + fta >= 3)
        o25o = _o25_odds(row)
        bttso = _btts_odds(row)
        combo_odds = None
        if o25o and bttso:
            combo_odds = round(o25o * bttso, 3)
        out.append(
            {
                "date": (row.get("Date") or "").strip(),
                "home": home,
                "away": away,
                "fth": fth,
                "fta": fta,
                "btts": btts,
                "o25": o25,
                "hit": int(btts == 1 and o25 == 1),
                "o25_odds": o25o,
                "btts_odds": bttso,
                "combo_odds": combo_odds,
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
    fh = [h["fh"] for h in history if h.get("fh") is not None]
    return {
        "n": n,
        "btts": 100.0 * sum(h["btts"] for h in history) / n,
        "o25": 100.0 * sum(h["o25"] for h in history) / n,
        "early": 100.0 * (sum(fh) / len(fh)) if fh else 50.0,
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
        rows.append(
            {
                "chaos": round(chaos_v1(h, a), 2),
                "hit": m["hit"],
                "btts": m["btts"],
                "o25": m["o25"],
                "o25_odds": m["o25_odds"],
                "btts_odds": m["btts_odds"],
                "combo_odds": m["combo_odds"],
            }
        )
        hist[m["home"]].append(
            {"gf": m["fth"], "ga": m["fta"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
        )
        hist[m["away"]].append(
            {"gf": m["fta"], "ga": m["fth"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
        )
    return rows


def hit_block(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    hits = sum(r["hit"] for r in rows)
    return {"n": n, "hits": hits, "hit_rate": round(100.0 * hits / n, 1)}


def combo_pnl(rows, stake=10.0, min_combo=None):
    trades = []
    for r in rows:
        od = r.get("combo_odds")
        if not od or od <= 1.01:
            continue
        if min_combo is not None and od < min_combo:
            continue
        profit = stake * (od - 1.0) if r["hit"] else -stake
        trades.append({"odds": od, "win": r["hit"], "profit": profit})
    if not trades:
        return {"trades": 0, "roi_pct": None}
    n = len(trades)
    wins = sum(t["win"] for t in trades)
    staked = stake * n
    profit = sum(t["profit"] for t in trades)
    return {
        "trades": n,
        "wins": wins,
        "hit_rate": round(100.0 * wins / n, 1),
        "avg_combo_odds": round(sum(t["odds"] for t in trades) / n, 3),
        "profit": round(profit, 2),
        "staked": round(staked, 2),
        "roi_pct": round(100.0 * profit / staked, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--min-trades", type=int, default=40)
    ap.add_argument("--form", type=int, default=8)
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.csv"))
    matches = []
    for f in files:
        matches.extend(parse_rows(f))
    matches.sort(key=lambda m: (_date_key(m["date"]), m["home"]))
    rows = build(matches, args.form)

    n = len(rows)
    with_o25 = sum(1 for r in rows if r.get("o25_odds"))
    with_btts = sum(1 for r in rows if r.get("btts_odds"))
    with_combo = sum(1 for r in rows if r.get("combo_odds"))

    baseline = hit_block(rows)
    bands = [
        ("all", 0, 101),
        ("micro_0_40", 0, 40),
        ("low_40_55", 40, 55),
        ("mid_55_70", 55, 70),
        ("high_70_80", 70, 80),
        ("elite_80_plus", 80, 101),
        ("high_70_plus", 70, 101),
    ]

    by_band = {}
    for name, lo, hi in bands:
        sub = [r for r in rows if lo <= r["chaos"] < hi]
        hb = hit_block(sub)
        hb["lift_pp"] = (
            round(hb["hit_rate"] - baseline["hit_rate"], 1)
            if hb.get("hit_rate") is not None
            else None
        )
        hb["combo_pnl"] = combo_pnl(sub, args.stake)
        by_band[name] = hb

    # Sweep min synthetic combo odds on high bands
    floors = [0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    sweep = []
    positives = []
    for name, lo, hi in bands:
        sub = [r for r in rows if lo <= r["chaos"] < hi]
        for floor in floors:
            stats = combo_pnl(sub, args.stake, min_combo=floor if floor else None)
            if stats.get("trades", 0) < args.min_trades:
                continue
            entry = {"band": name, "min_combo_odds": floor, **stats}
            sweep.append(entry)
            if stats.get("roi_pct") is not None and stats["roi_pct"] > 0:
                positives.append(entry)

    positives.sort(key=lambda x: x["roi_pct"], reverse=True)
    sweep.sort(key=lambda x: (x.get("roi_pct") is not None, x.get("roi_pct") or -999), reverse=True)

    out = {
        "disclaimer": (
            "combo_odds = o25_odds * btts_odds (SYNTHETIC). "
            "Real correlated combo prices are tighter; ROI is optimistic."
        ),
        "coverage": {
            "scored": n,
            "with_o25_odds": with_o25,
            "with_btts_odds": with_btts,
            "with_combo": with_combo,
            "combo_pct": round(100.0 * with_combo / n, 1) if n else 0,
        },
        "baseline_btts_and_o25": baseline,
        "by_band": by_band,
        "positive_roi_slices": positives[:15],
        "positive_count": len(positives),
        "top_roi_slices": sweep[:12],
    }
    print(json.dumps(out, indent=2))

    if with_combo < 50:
        print(
            "\nNOTE: Very few rows have both O2.5 and strict BTTS odds. "
            "football-data often lacks BTTS columns — combo P/L may be empty.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
