#!/usr/bin/env python3
"""
Chaos v2 backtest — hit-rate + O2.5 P/L for v1 vs v2 vs league residual.

Usage:
  python3 -u scripts/backtest_chaos_v2.py --dir data/football_data --min-score 70
  python3 -u scripts/backtest_chaos_v2.py --dir data/football_data --top-pct 15 --stake 10
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


def _o25_odds(row) -> float | None:
    odds = _f(
        row,
        "B365>2.5",
        "P>2.5",
        "PS>2.5",
        "Avg>2.5",
        "BbAv>2.5",
        "Max>2.5",
        "B365C>2.5",
    )
    if odds is not None and 1.01 < odds < 10:
        return odds
    for k, v in row.items():
        if v and ">2.5" in k:
            try:
                cand = float(str(v).strip())
                if 1.01 < cand < 10:
                    return cand
            except ValueError:
                pass
    return None


def parse_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
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
                "o25_odds": _o25_odds(row),
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
    exp_home_goals = (h["gf"] + a["ga"]) / 2.0
    exp_away_goals = (a["gf"] + h["ga"]) / 2.0
    exp_total = exp_home_goals + exp_away_goals
    o25_proxy = min(100.0, max(0.0, (exp_total - 1.5) / 2.5 * 100.0))
    btts_proxy = (
        0.5 * ((h["scored"] + a["conceded"]) / 2.0)
        + 0.5 * ((a["scored"] + h["conceded"]) / 2.0)
    )
    early = (h["early"] + a["early"]) / 2.0
    vol = min(100.0, exp_total * 28.0)
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


def o25_pnl(selected: list[dict], stake: float) -> dict:
    """Flat-stake back Over 2.5 when odds present."""
    trades = []
    for r in selected:
        odds = r.get("o25_odds")
        if not odds or odds <= 1.01:
            continue
        profit = stake * (odds - 1.0) if r.get("o25") else -stake
        trades.append(
            {
                "odds": odds,
                "win": int(r.get("o25") == 1),
                "profit": profit,
            }
        )
    n = len(trades)
    if not n:
        return {
            "trades": 0,
            "wins": 0,
            "hit_rate": None,
            "avg_odds": None,
            "staked": 0.0,
            "profit": 0.0,
            "roi_pct": None,
        }
    wins = sum(t["win"] for t in trades)
    staked = stake * n
    profit = sum(t["profit"] for t in trades)
    avg_odds = sum(t["odds"] for t in trades) / n
    return {
        "trades": n,
        "wins": wins,
        "hit_rate": _rate(wins, n),
        "avg_odds": round(avg_odds, 3),
        "staked": round(staked, 2),
        "profit": round(profit, 2),
        "roi_pct": round(100.0 * profit / staked, 2),
    }


def run(matches, form_n: int):
    hist = defaultdict(lambda: deque(maxlen=form_n))
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

        lh = list(league_hist[m["league"]])
        if len(lh) >= 30:
            base_o25 = 100.0 * sum(x["o25"] for x in lh) / len(lh)
            base_btts = 100.0 * sum(x["btts"] for x in lh) / len(lh)
            league_open = 0.5 * base_o25 + 0.5 * base_btts
        else:
            league_open = 50.0

        s2_resid = max(0.0, min(100.0, s2 - 0.35 * (league_open - 50.0)))

        rows.append(
            {
                **{k: m[k] for k in MARKETS},
                "league": m["league"],
                "date": m["date"],
                "match": f'{m["home"]} vs {m["away"]}',
                "o25_odds": m.get("o25_odds"),
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


def evaluate(rows, score_key: str, top_pct, min_score, stake: float):
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

    pnl = o25_pnl(selected, stake)

    return {
        "score": score_key,
        "select_mode": mode,
        "baseline": baseline,
        "selected": sel,
        "lift_pp": lifts,
        "o25_pnl": pnl,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    p.add_argument("--form", type=int, default=8)
    p.add_argument("--min-score", type=float, default=70.0)
    p.add_argument("--top-pct", type=float, default=None)
    p.add_argument("--stake", type=float, default=10.0)
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
        "stake": args.stake,
        "v1_avg": evaluate(rows, "v1", args.top_pct, args.min_score, args.stake),
        "v2_matchup": evaluate(rows, "v2", args.top_pct, args.min_score, args.stake),
        "v2_matchup_league_resid": evaluate(
            rows, "v2_resid", args.top_pct, args.min_score, args.stake
        ),
    }

    summary = {}
    for name in ("v1_avg", "v2_matchup", "v2_matchup_league_resid"):
        block = report[name]
        pnl = block["o25_pnl"]
        summary[name] = {
            "selected_n": block["selected"].get("n"),
            "lift_btts_o25": block["lift_pp"].get("btts_o25"),
            "lift_o25": block["lift_pp"].get("o25"),
            "o25_hit_selected": block["selected"].get("o25"),
            "o25_trades": pnl["trades"],
            "o25_hit_rate": pnl["hit_rate"],
            "avg_odds": pnl["avg_odds"],
            "staked": pnl["staked"],
            "profit": pnl["profit"],
            "roi_pct": pnl["roi_pct"],
        }
    report["comparison"] = summary

    # Fair top-15% P/L head-to-head always printed in comparison_top15
    t15 = {}
    for key, label in (("v1", "v1_avg"), ("v2", "v2_matchup"), ("v2_resid", "v2_matchup_league_resid")):
        block = evaluate(rows, key, 15.0, None, args.stake)
        pnl = block["o25_pnl"]
        t15[label] = {
            "selected_n": block["selected"].get("n"),
            "lift_o25": block["lift_pp"].get("o25"),
            "lift_btts_o25": block["lift_pp"].get("btts_o25"),
            "o25_trades": pnl["trades"],
            "avg_odds": pnl["avg_odds"],
            "profit": pnl["profit"],
            "roi_pct": pnl["roi_pct"],
            "hit_rate": pnl["hit_rate"],
        }
    report["comparison_top15pct"] = t15

    print(json.dumps({"comparison": summary, "comparison_top15pct": t15}, indent=2))


if __name__ == "__main__":
    main()
