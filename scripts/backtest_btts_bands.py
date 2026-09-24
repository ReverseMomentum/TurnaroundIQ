#!/usr/bin/env python3
"""
BTTS profitability / hit-rate by Chaos v1 score band.

- Always reports BTTS hit rate by band (from FT scores).
- Where BTTS Yes odds exist in football-data CSVs, also flat-stake ROI.
- Sweeps odds floors to hunt positive ROI slices.

Usage:
  python3 -u scripts/backtest_btts_bands.py --dir data/football_data
  python3 -u scripts/backtest_btts_bands.py --dir data/football_data --min-trades 100
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


def _btts_odds(row):
    """BTTS Yes odds — column names vary by season/source."""
    odds = _f(
        row,
        "B365BTTS",
        "B365BTTSY",
        "BTTS",
        "BTTSY",
        "BbAvBTTS",
        "AvgBTTS",
        "PSBTTS",
        "B365CH",
    )
    if odds and 1.01 < odds < 8:
        return odds
    for k, v in row.items():
        if not v:
            continue
        kl = k.lower()
        if "btts" in kl and "n" not in kl.split("btts")[-1][:2]:
            try:
                c = float(str(v).strip())
                if 1.01 < c < 8:
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
        out.append(
            {
                "date": (row.get("Date") or "").strip(),
                "home": home,
                "away": away,
                "fth": fth,
                "fta": fta,
                "btts": btts,
                "o25": int(fth + fta >= 3),
                "btts_odds": _btts_odds(row),
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
                "btts": m["btts"],
                "btts_odds": m["btts_odds"],
            }
        )
        hist[m["home"]].append(
            {"gf": m["fth"], "ga": m["fta"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
        )
        hist[m["away"]].append(
            {"gf": m["fta"], "ga": m["fth"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
        )
    return rows


def hit_stats(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    hits = sum(r["btts"] for r in rows)
    return {"n": n, "hits": hits, "hit_rate": round(100.0 * hits / n, 1)}


def pnl(rows, stake=10.0):
    trades = [r for r in rows if r.get("btts_odds") and r["btts_odds"] > 1.01]
    if not trades:
        return {"trades": 0, "roi_pct": None, "note": "no BTTS odds in slice"}
    profit = sum(stake * (r["btts_odds"] - 1) if r["btts"] else -stake for r in trades)
    staked = stake * len(trades)
    wins = sum(1 for r in trades if r["btts"])
    return {
        "trades": len(trades),
        "wins": wins,
        "hit_rate": round(100.0 * wins / len(trades), 1),
        "avg_odds": round(sum(r["btts_odds"] for r in trades) / len(trades), 3),
        "profit": round(profit, 2),
        "staked": round(staked, 2),
        "roi_pct": round(100.0 * profit / staked, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--min-trades", type=int, default=80)
    ap.add_argument("--form", type=int, default=8)
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.csv"))
    matches = []
    for f in files:
        matches.extend(parse_rows(f))
    matches.sort(key=lambda m: (_date_key(m["date"]), m["home"]))
    rows = build(matches, args.form)

    with_odds = sum(1 for r in rows if r.get("btts_odds"))
    print(f"scored={len(rows)} with_btts_odds={with_odds}")

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

    baseline = hit_stats(rows)
    by_band = {}
    for name, lo, hi in bands:
        subset = [r for r in rows if lo <= r["chaos"] < hi]
        hs = hit_stats(subset)
        hs["lift_pp"] = (
            round(hs["hit_rate"] - baseline["hit_rate"], 1)
            if hs.get("hit_rate") is not None and baseline.get("hit_rate") is not None
            else None
        )
        hs["pnl_all_odds"] = pnl(subset, args.stake)
        by_band[name] = hs

    # Odds floor sweep on high bands
    floors = [0, 1.50, 1.60, 1.70, 1.80, 1.90, 2.00]
    sweep = []
    positives = []
    for name, lo, hi in bands:
        band_rows = [r for r in rows if lo <= r["chaos"] < hi]
        for floor in floors:
            sub = [
                r
                for r in band_rows
                if r.get("btts_odds") and r["btts_odds"] >= floor
            ]
            stats = pnl(sub, args.stake)
            if stats.get("trades", 0) < args.min_trades:
                continue
            entry = {"band": name, "min_odds": floor, **stats}
            sweep.append(entry)
            if stats.get("roi_pct") is not None and stats["roi_pct"] > 0:
                positives.append(entry)

    positives.sort(key=lambda x: x["roi_pct"], reverse=True)
    sweep.sort(key=lambda x: (x.get("roi_pct") is not None, x.get("roi_pct") or -999), reverse=True)

    out = {
        "baseline_btts": baseline,
        "odds_coverage": {
            "rows": len(rows),
            "with_btts_odds": with_odds,
            "pct": round(100.0 * with_odds / len(rows), 1) if rows else 0,
        },
        "by_band_hit_rate": by_band,
        "positive_roi_slices": positives[:15],
        "positive_count": len(positives),
        "top_roi_slices": sweep[:12],
        "note": (
            "Hit rates use all games. ROI only where BTTS Yes odds were present "
            "in football-data CSVs (often sparse)."
        ),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
