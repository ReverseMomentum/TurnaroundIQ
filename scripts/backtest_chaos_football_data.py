#!/usr/bin/env python3
"""
Walk-forward Chaos backtest from football-data.co.uk CSVs.

Reports hit rates by chaos band for:
  - O2.5
  - BTTS
  - BTTS + O2.5 (paper Chaos settle)
  - O3.5

Also paper-backs O2.5 when chaos >= threshold (if odds present).

Usage:
  python -u scripts/backtest_chaos_football_data.py --dir data/football_data --min-chaos 70
  python -u scripts/backtest_chaos_football_data.py --download --seasons 2223,2324,2425
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DIVS = ["E0", "E1", "SP1", "I1", "D1", "F1", "N1", "P1", "SC0"]
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"

MARKETS = ("o25", "btts", "btts_o25", "o35")


def _season_path(season: str) -> str:
    s = season.strip().replace("/", "")
    return s if len(s) >= 4 else s


def download_csv(season: str, div: str, out_dir: Path) -> Path | None:
    season = _season_path(season)
    url = BASE_URL.format(season=season, div=div)
    dest = out_dir / f"{season}_{div}.csv"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        if len(data) < 200 or b"404" in data[:50].lower():
            print(f"  skip {div} {season}: empty/404")
            return None
        dest.write_bytes(data)
        print(f"  saved {dest.name} ({len(data)} bytes)")
        return dest
    except Exception as exc:
        print(f"  fail {div} {season}: {exc}")
        return None


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
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        home = (row.get("HomeTeam") or row.get("Home") or "").strip()
        away = (row.get("AwayTeam") or row.get("Away") or "").strip()
        if not home or not away:
            continue
        fth = _i(row, "FTHG", "HG")
        fta = _i(row, "FTAG", "AG")
        if fth is None or fta is None:
            continue
        hth = _i(row, "HTHG")
        hta = _i(row, "HTAG")
        o25_odds = _f(
            row,
            "B365>2.5",
            "P>2.5",
            "PS>2.5",
            "Avg>2.5",
            "BbAv>2.5",
            "Max>2.5",
            "B365C>2.5",
        )
        if o25_odds is None:
            for k, v in row.items():
                if v and ">2.5" in k:
                    try:
                        cand = float(str(v).strip())
                        if 1.01 < cand < 10:
                            o25_odds = cand
                            break
                    except ValueError:
                        pass
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
                "hth": hth,
                "hta": hta,
                "o25_odds": o25_odds,
                "div": path.stem,
                "btts": btts,
                "o25": o25,
                "o35": o35,
                "btts_o25": int(btts == 1 and o25 == 1),
                "fh_goal": (
                    int((hth + hta) > 0)
                    if hth is not None and hta is not None
                    else None
                ),
            }
        )
    return out


def _parse_date_key(date_s: str) -> tuple:
    parts = date_s.replace("-", "/").split("/")
    if len(parts) != 3:
        return (9999, 99, 99)
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        if y < 100:
            y += 2000 if y < 70 else 1900
        return (y, m, d)
    except ValueError:
        return (9999, 99, 99)


def team_form_rates(history: deque) -> dict:
    n = len(history)
    if n == 0:
        return {"n": 0, "btts": 50.0, "o25": 50.0, "early": 50.0, "goals": 1.2}
    btts = 100.0 * sum(h["btts"] for h in history) / n
    o25 = 100.0 * sum(h["o25"] for h in history) / n
    fh = [h["fh_goal"] for h in history if h.get("fh_goal") is not None]
    early = 100.0 * (sum(fh) / len(fh)) if fh else 50.0
    goals = sum(h.get("goals_for", 0) + h.get("goals_against", 0) for h in history) / n
    return {"n": n, "btts": btts, "o25": o25, "early": early, "goals": goals}


def chaos_score(home_rates, away_rates) -> float:
    o2_5 = (home_rates["o25"] + away_rates["o25"]) / 2.0
    btts = (home_rates["btts"] + away_rates["btts"]) / 2.0
    early = (home_rates["early"] + away_rates["early"]) / 2.0
    vol = min(100.0, ((home_rates["goals"] + away_rates["goals"]) / 2.0) * 25.0)
    score = 0.28 * o2_5 + 0.28 * btts + 0.22 * early + 0.22 * vol
    return round(max(0.0, min(100.0, score)), 2)


def band(score: float) -> str:
    if score >= 70:
        return "high_70plus"
    if score >= 55:
        return "mid_55_70"
    if score >= 40:
        return "low_40_55"
    return "micro_under_40"


def _push(hist, m):
    hist[m["home"]].append(
        {
            "btts": m["btts"],
            "o25": m["o25"],
            "fh_goal": m["fh_goal"],
            "goals_for": m["fth"],
            "goals_against": m["fta"],
        }
    )
    hist[m["away"]].append(
        {
            "btts": m["btts"],
            "o25": m["o25"],
            "fh_goal": m["fh_goal"],
            "goals_for": m["fta"],
            "goals_against": m["fth"],
        }
    )


def run_backtest(matches: list[dict], form_n: int, min_chaos: float, stake: float):
    hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=form_n))
    results = []

    for m in matches:
        hr = team_form_rates(hist[m["home"]])
        ar = team_form_rates(hist[m["away"]])
        if hr["n"] < max(3, form_n // 3) or ar["n"] < max(3, form_n // 3):
            _push(hist, m)
            continue

        score = chaos_score(hr, ar)
        o25_odds = m.get("o25_odds")
        selected = score >= min_chaos

        row = {
            "date": m["date"],
            "match": f'{m["home"]} vs {m["away"]}',
            "div": m["div"],
            "chaos": score,
            "band": band(score),
            "selected": selected,
            "o25": m["o25"],
            "btts": m["btts"],
            "btts_o25": m["btts_o25"],
            "o35": m["o35"],
            "o25_odds": o25_odds,
        }

        if selected and o25_odds and o25_odds > 1.01:
            row["o25_profit"] = round(
                stake * (o25_odds - 1.0) if m["o25"] else -stake, 2
            )
            row["o25_staked"] = stake
        else:
            row["o25_profit"] = None
            row["o25_staked"] = 0.0

        results.append(row)
        _push(hist, m)

    return results


def _rate(hits, n):
    return round(100.0 * hits / n, 1) if n else None


def _market_block(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    out = {"n": n}
    for mkt in MARKETS:
        hits = sum(int(r[mkt]) for r in rows)
        out[mkt] = _rate(hits, n)
        out[f"{mkt}_hits"] = hits
    return out


def summarise(results: list[dict], min_chaos: float) -> dict:
    by_band_rows = defaultdict(list)
    for r in results:
        by_band_rows[r["band"]].append(r)

    by_band = {name: _market_block(rows) for name, rows in sorted(by_band_rows.items())}
    baseline = _market_block(results)
    selected = [r for r in results if r["selected"]]
    selected_block = _market_block(selected)

    lifts = {}
    for mkt in MARKETS:
        b = baseline.get(mkt)
        s = selected_block.get(mkt)
        lifts[mkt] = round(s - b, 1) if b is not None and s is not None else None

    o25_trades = [r for r in selected if r.get("o25_profit") is not None]
    staked = sum(r["o25_staked"] for r in o25_trades)
    profit = sum(r["o25_profit"] for r in o25_trades)
    o25_wins = sum(1 for r in o25_trades if r["o25"] == 1)

    return {
        "matches_scored": len(results),
        "min_chaos": min_chaos,
        "baseline": baseline,
        "selected": selected_block,
        "lift_pp_vs_baseline": lifts,
        "by_band": by_band,
        "o25_priced_backtest": {
            "trades": len(o25_trades),
            "wins": o25_wins,
            "hit_rate": _rate(o25_wins, len(o25_trades)),
            "staked": round(staked, 2),
            "profit": round(profit, 2),
            "roi_pct": round(100.0 * profit / staked, 2) if staked else None,
            "note": "Back Over 2.5 only when chaos >= min (not combo price)",
        },
    }


def main():
    p = argparse.ArgumentParser(description="Chaos backtest via football-data CSVs")
    p.add_argument("--dir", default=str(ROOT / "data" / "football_data"))
    p.add_argument("--download", action="store_true")
    p.add_argument("--seasons", default="2223,2324,2425")
    p.add_argument("--divs", default=",".join(DEFAULT_DIVS))
    p.add_argument("--form", type=int, default=8)
    p.add_argument("--min-chaos", type=float, default=55.0)
    p.add_argument("--stake", type=float, default=10.0)
    p.add_argument("--top", type=int, default=0)
    args = p.parse_args()

    out_dir = Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.download:
        print("Downloading football-data CSVs…")
        for season in [s.strip() for s in args.seasons.split(",") if s.strip()]:
            for div in [d.strip() for d in args.divs.split(",") if d.strip()]:
                download_csv(season, div, out_dir)

    files = sorted(out_dir.glob("*.csv"))
    if not files:
        print(f"No CSVs in {out_dir}. Re-run with --download.")
        sys.exit(1)

    matches = []
    for f in files:
        rows = parse_rows(f)
        print(f"Loaded {f.name}: {len(rows)} matches")
        matches.extend(rows)

    matches.sort(key=lambda m: (_parse_date_key(m["date"]), m["home"], m["away"]))
    print(f"Total matches: {len(matches)}")

    results = run_backtest(matches, form_n=args.form, min_chaos=args.min_chaos, stake=args.stake)
    summary = summarise(results, args.min_chaos)

    if args.top:
        top = sorted(results, key=lambda r: r["chaos"], reverse=True)[: args.top]
        summary["examples"] = [
            {
                "match": r["match"],
                "chaos": r["chaos"],
                "o25": r["o25"],
                "btts": r["btts"],
                "btts_o25": r["btts_o25"],
                "o35": r["o35"],
            }
            for r in top
        ]

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
