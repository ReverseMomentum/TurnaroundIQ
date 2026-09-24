#!/usr/bin/env python3
"""
Chaos v2 backtest — high-ROI methodology upgrades vs v1 form average.

Upgrades:
  1. Matchup terms (attack vs opponent concede proxy) instead of plain average
  2. League baseline residual (chaos relative to division base rates)
  3. Calibration table: empirical P(event) by score decile
  4. Top-tail selection (top pct of slate) vs fixed threshold

Reuses CSVs from data/football_data (same as v1).

Usage:
  python3 -u scripts/backtest_chaos_v2.py --dir data/football_data
  python3 -u scripts/backtest_chaos_v2.py --dir data/football_data --top-pct 15
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
MARKETS = ("o25", "btts", "btts_o25", "o35")


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


def parse_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    # league code from filename e.g. 2425_E0.csv
    stem = path.stem
    league = stem.split("_")[-1] if "_" in stem else stem
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
        btts = int(fth > 0 and fta > 0)
        o25 = int(goals >= 3)
        o35 = int(goals >= 4)
        out.append(
            {
                "date": (row.get("Date") or "").strip(),
                "home": home,
                "away": away,
                "fth": fth,
                "fta": fta,
                "league": league,
                "btts": btts,
                "o25": o25,
                "o35": o35,
                "btts_o25": int(btts and o25),
                "fh_goal": (
                    int((hth + hta) > 0)
                    if hth is not None and hta is not None
                    else None
                ),
            }
        )
    return out


def _date_key(s: str):
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


def form_side(history: deque) -> dict:
    """Attack/defence style rates from prior games for one team."""
    n = len(history)
    if n == 0:
        return {
            "n": 0,
            "gf": 1.2,
            "ga": 1.2,
            "btts": 50.0,
            "o25": 50.0,
            "early": 50.0,
            "scored": 50.0,
            "conceded": 50.0,
        }
    gf = sum(h["gf"] for h in history) / n
    ga = sum(h["ga"] for h in history) / n
    btts = 100.0 * sum(h["btts"] for h in history) / n
    o25 = 100.0 * sum(h["o25"] for h in history) / n
    scored = 100.0 * sum(1 for h in history if h["gf"] > 0) / n
    conceded = 100.0 * sum(1 for h in history if h["ga"] > 0) / n
    fh = [h["fh"] for h in history if h.get("fh") is not None]
    early = 100.0 * (sum(fh) / len(fh)) if fh else 50.0
    return {
        "n": n,
        "gf": gf,
        "ga": ga,
        "btts": btts,
        "o25": o25,
        "early": early,
        "scored": scored,
        "conceded": conceded,
    }


def chaos_v1_avg(h, a) -> float:
    o2 = (h["o25"] + a["o25"]) / 2
    bt = (h["btts"] + a["btts"]) / 2
    early = (h["early"] + a["early"]) / 2
    vol = min(100.0, ((h["gf"] + h["ga"] + a["gf"] + a["ga"]) / 2) * 12.5)
    return 0.28 * o2 + 0.28 * bt + 0.22 * early + 0.22 * vol


def chaos_v2_matchup(h, a) -> float:
    """
    Matchup-aware:
      - expected openness from attack vs opp defence
      - BTTS proxy: both sides score rate × opp concede rate
      - early average
      - goal expectation volume
    """
    # Goal expectation proxies (scaled to ~0-100-ish contribution inputs)
    exp_home_goals = (h["gf"] + a["ga"]) / 2.0
    exp_away_goals = (a["gf"] + h["ga"]) / 2.0
    exp_total = exp_home_goals + exp_away_goals  # ~2-3.5 typical

    o25_proxy = min(100.0, max(0.0, (exp_total - 1.5) / 2.5 * 100.0))
    # BTTS: chance both score ~ product-ish of score/concede tendencies
    btts_proxy = (
        0.5 * ((h["scored"] + a["conceded"]) / 2.0)
        + 0.5 * ((a["scored"] + h["conceded"]) / 2.0)
    )
    early = (h["early"] + a["early"]) / 2.0
    vol = min(100.0, exp_total * 28.0)

    # slight blend with pure form o25/btts so we don't go pure theoretical
    o25_form = (h["o25"] + a["o25"]) / 2.0
    btts_form = (h["btts"] + a["btts"]) / 2.0
    o25 = 0.55 * o25_proxy + 0.45 * o25_form
    btts = 0.55 * btts_proxy + 0.45 * btts_form

    return 0.30 * o25 + 0.28 * btts + 0.20 * early + 0.22 * vol


def push(hist, m):
    hist[m["home"]].append(
        {"gf": m["fth"], "ga": m["fta"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
    )
    hist[m["away"]].append(
        {"gf": m["fta"], "ga": m["fth"], "btts": m["btts"], "o25": m["o25"], "fh": m["fh_goal"]}
    )


def _rate(hits, n):
    return round(100.0 * hits / n, 1) if n else None


def market_rates(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    out = {"n": n}
    for k in MARKETS:
        out[k] = _rate(sum(r[k] for r in rows), n)
    return out


def run(matches, form_n: int):
    hist = defaultdict(lambda: deque(maxlen=form_n))
    # rolling league base rates (prior matches in same league only)
    league_hist = defaultdict(lambda: deque(maxlen=400))
    rows = []

    for m in matches:
        h = form_side(hist[m["home"]])
        a = form_side(hist[m["away"]])
        if h["n"] < max(3, form_n // 3) or a["n"] < max(3, form_n // 3):
            push(hist, m)
            league_hist[m["league"]].append(m)
            continue

        s1 = chaos_v1_avg(h, a)
        s2 = chaos_v2_matchup(h, a)

        # league baseline residual: how hot is this league lately?
        lh = list(league_hist[m["league"]])
        if len(lh) >= 30:
            base_o25 = 100.0 * sum(x["o25"] for x in lh) / len(lh)
            base_btts = 100.0 * sum(x["btts"] for x in lh) / len(lh)
            league_open = 0.5 * base_o25 + 0.5 * base_btts
        else:
            league_open = 50.0

        # residual boost: matchup score relative to league climate
        s2_resid = s2 - 0.35 * (league_open - 50.0)
        s2_resid = max(0.0, min(100.0, s2_resid))

        rows.append(
            {
                **{k: m[k] for k in MARKETS},
                "league": m["league"],
                "date": m["date"],
                "match": f'{m["home"]} vs {m["away"]}',
                "v1": round(s1, 2),
                "v2": round(s2, 2),
                "v2_resid": round(s2_resid, 2),
            }
        )
        push(hist, m)
        league_hist[m["league"]].append(m)

    return rows


def band(score, edges=(40, 55, 70)):
    if score >= edges[2]:
        return "high"
    if score >= edges[1]:
        return "mid"
    if score >= edges[0]:
        return "low"
    return "micro"


def evaluate(rows, score_key: str, top_pct: float | None, min_score: float | None):
    baseline = market_rates(rows)

    if top_pct is not None:
        n_top = max(1, int(len(rows) * top_pct / 100.0))
        ranked = sorted(rows, key=lambda r: r[score_key], reverse=True)
        selected = ranked[:n_top]
        mode = f"top_{top_pct}pct"
    else:
        selected = [r for r in rows if r[score_key] >= (min_score or 70)]
        mode = f"min_{min_score}"

    by_band = defaultdict(list)
    for r in rows:
        by_band[band(r[score_key])].append(r)

    band_stats = {b: market_rates(rs) for b, rs in sorted(by_band.items())}
    sel = market_rates(selected)
    lifts = {
        k: round(sel[k] - baseline[k], 1)
        if sel.get(k) is not None and baseline.get(k) is not None
        else None
        for k in MARKETS
    }

    # calibration: deciles of score → empirical btts_o25
    ranked = sorted(rows, key=lambda r: r[score_key])
    deciles = []
    chunk = max(1, len(ranked) // 10)
    for i in range(10):
        part = ranked[i * chunk : (i + 1) * chunk] if i < 9 else ranked[i * chunk :]
        if not part:
            continue
        scores = [r[score_key] for r in part]
        deciles.append(
            {
                "decile": i + 1,
                "score_lo": round(min(scores), 1),
                "score_hi": round(max(scores), 1),
                "n": len(part),
                "p_btts_o25": market_rates(part).get("btts_o25"),
                "p_o25": market_rates(part).get("o25"),
                "p_o35": market_rates(part).get("o35"),
            }
        )

    return {
        "score": score_key,
        "select_mode": mode,
        "baseline": baseline,
        "selected": sel,
        "lift_pp": lifts,
        "by_band": band_stats,
        "calibration_deciles": deciles,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    p.add_argument("--form", type=int, default=8)
    p.add_argument("--min-score", type=float, default=70.0)
    p.add_argument("--top-pct", type=float, default=None, help="e.g. 15 = top 15% of scores")
    args = p.parse_args()

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

    report = {
        "n": len(rows),
        "v1_avg": evaluate(rows, "v1", args.top_pct, args.min_score),
        "v2_matchup": evaluate(rows, "v2", args.top_pct, args.min_score),
        "v2_matchup_league_resid": evaluate(rows, "v2_resid", args.top_pct, args.min_score),
    }

    # head-to-head summary of lifts on btts_o25
    summary = {}
    for name, block in report.items():
        if name == "n":
            continue
        summary[name] = {
            "lift_btts_o25": block["lift_pp"].get("btts_o25"),
            "lift_o25": block["lift_pp"].get("o25"),
            "lift_o35": block["lift_pp"].get("o35"),
            "lift_btts": block["lift_pp"].get("btts"),
            "selected_n": block["selected"].get("n"),
            "selected_btts_o25": block["selected"].get("btts_o25"),
        }
    report["comparison"] = summary

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
