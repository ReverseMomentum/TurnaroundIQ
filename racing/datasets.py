"""
Readers for free historical results, turned into the race dicts that
racing/calibrate.py and racing/backtest.py use:

  {"key", "date", "course", "country", "handicap", "runners": [{"name", "odds"}],
   "order": [runner indices, 1st first], "finish": [position or None per runner]}

Supported:
  Kaggle hwaitt/horse-racing      races_YYYY.csv + horses_YYYY.csv (1990-2020)
                                  decimalPrice is 1/odds; position 40 = did not finish
  Kaggle deltaromeo UK/IRE        SQLite (or CSV) in rpscrape layout: date, region,
                                  course, off, race_name, horse, pos, sp / dec
  Any CSV with similar columns    matched through the alias lists below

Races are dropped when a runner has no usable price, or with fewer than 5 runners.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

MIN_RUNNERS = 5

ALIASES = {
    "race": ["rid", "race_id", "raceid"],
    "date": ["date", "race_date", "meeting_date"],
    "time": ["time", "off", "off_time"],
    "course": ["course", "track", "venue"],
    "country": ["countrycode", "region", "country"],
    "title": ["title", "race_name", "racename", "name"],
    "horse": ["horsename", "horse", "horse_name", "runner"],
    "pos": ["position", "pos", "finish_position", "fin_pos"],
    "implied": ["decimalprice"],            # hwaitt: 1 / decimal odds
    "dec": ["dec", "sp_dec", "decimal_sp", "odds", "bsp"],
    "sp": ["sp", "starting_price", "isp"],
}
DEFAULT_COUNTRIES = {"GB", "GB-ENG", "UK", "IRE", "IE", "IRL", "ENG", "SCO", "WAL"}


def _pick(cols: Iterable[str], key: str) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for a in ALIASES[key]:
        if a in lower:
            return lower[a]
    return None


def parse_sp(v) -> Optional[float]:
    """'9/2F', '11/10JF', 'Evens', 'EvsF', '4.5' -> decimal odds."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v and v > 1 else None
    s = str(v).strip().lower()
    if not s or s in ("nan", "-"):
        return None
    if s.startswith("ev"):
        return 2.0
    m = re.match(r"^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", s)
    if m:
        den = float(m.group(2))
        return 1.0 + float(m.group(1)) / den if den else None
    m = re.match(r"^(\d+(?:\.\d+)?)", s)
    if m and float(m.group(1)) > 1:
        return float(m.group(1))
    return None


def parse_pos(v) -> Optional[int]:
    """'1', 1.0, '3=' (dead heat) -> int; 'PU', 'F', 40 (hwaitt non-finisher) -> None."""
    if v is None:
        return None
    m = re.match(r"^\s*(\d+)", str(v))
    if not m:
        return None
    p = int(m.group(1))
    return p if 1 <= p < 40 else None


def _frames(paths: list[Path]) -> Iterable[pd.DataFrame]:
    """Yield one runner-level DataFrame per source file (hwaitt pairs are joined)."""
    files = []
    for p in paths:
        files.extend(sorted(p.rglob("*")) if p.is_dir() else [p])
    races = {re.sub(r"\D", "", f.stem): f for f in files if f.name.lower().startswith("races_") and f.suffix == ".csv"}
    for f in files:
        name = f.name.lower()
        if name.startswith("horses_") and f.suffix == ".csv":
            h = pd.read_csv(f, low_memory=False)
            r = races.get(re.sub(r"\D", "", f.stem))
            if r is not None:
                rr = pd.read_csv(r, low_memory=False)
                keep = [c for c in rr.columns if c not in h.columns or c == "rid"]
                h = h.merge(rr[keep], on="rid", how="left")
            yield h
        elif name.startswith("races_"):
            continue
        elif f.suffix == ".csv":
            yield pd.read_csv(f, low_memory=False)
        elif f.suffix in (".db", ".sqlite", ".sqlite3"):
            con = sqlite3.connect(f)
            tables = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
                if _pick(cols, "horse") and _pick(cols, "pos"):
                    for chunk in pd.read_sql_query(f'SELECT * FROM "{t}"', con, chunksize=500_000):
                        yield chunk
            con.close()


DATE_FORMATS = ("ISO8601", "%y/%m/%d %H:%M", "%y/%m/%d", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%d-%m-%Y %H:%M", "%d-%m-%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y")


def parse_dates(col: pd.Series) -> pd.Series:
    """Try each explicit format and keep the one that parses the most rows (no guessing per row)."""
    best, best_ok = None, -1
    raw = col.astype(str).str.strip()
    for fmt in DATE_FORMATS:
        try:
            d = pd.to_datetime(raw, format=fmt, errors="coerce", utc=True)
        except (ValueError, TypeError):
            continue
        ok = int(d.notna().sum())
        if ok > best_ok:
            best, best_ok = d, ok
        if ok == len(raw):
            break
    return best.dt.tz_localize(None) if best is not None else pd.Series(pd.NaT, index=col.index)


def odds_from_price_column(v: pd.Series) -> pd.Series:
    """hwaitt decimalPrice: 1/odds in the results files, real odds in forward.csv. Decide from the values."""
    x = pd.to_numeric(v, errors="coerce")
    if x.dropna().median() < 1:
        return 1.0 / x.where(x > 0)
    return x


def peek(paths: list[Path]) -> str:
    """Columns, how each was matched, and parsed samples, for the first results file found."""
    for df in _frames(paths):
        if not (_pick(df.columns, "horse") and _pick(df.columns, "pos")):
            continue
        lines = [f"{len(df)} rows; columns: {', '.join(map(str, df.columns))}"]
        for key in ALIASES:
            lines.append(f"  {key:<8} -> {_pick(df.columns, key)}")
        dc = _pick(df.columns, "date")
        if dc:
            d = parse_dates(df[dc])
            lines.append(f"  dates: {df[dc].iloc[0]!r} -> {d.iloc[0]}  ({int(d.notna().sum())}/{len(d)} parsed, "
                         f"{d.min()} to {d.max()})")
        pc = _pick(df.columns, "implied") or _pick(df.columns, "dec")
        if pc:
            o = odds_from_price_column(df[pc]) if pc == _pick(df.columns, "implied") else pd.to_numeric(df[pc], errors="coerce")
            lines.append(f"  odds: {df[pc].iloc[0]!r} -> {o.iloc[0]:.2f}  (median {o.median():.2f})")
        lines.append(df.head(3).to_string()[:1500])
        return "\n".join(lines)
    return "no results files found (need a horse column and a finishing position column)"


def load_races(paths: list[Path], years: Optional[tuple[int, int]] = None,
               countries: Optional[set] = DEFAULT_COUNTRIES) -> list[dict]:
    out = []
    for df in _frames(paths):
        col = {k: _pick(df.columns, k) for k in ALIASES}
        if not col["horse"] or not col["pos"] or not col["date"]:
            continue
        df = df.copy()
        df["_date"] = parse_dates(df[col["date"]])
        df = df[df["_date"].notna()]
        if years:
            df = df[(df["_date"].dt.year >= years[0]) & (df["_date"].dt.year <= years[1])]
        if countries and col["country"]:
            df = df[df[col["country"]].astype(str).str.upper().str.strip().isin(countries)]
        if df.empty:
            continue
        if col["implied"]:
            df["_odds"] = odds_from_price_column(df[col["implied"]])
        elif col["dec"]:
            df["_odds"] = pd.to_numeric(df[col["dec"]], errors="coerce")
        else:
            df["_odds"] = None
        if col["sp"]:
            df["_odds"] = df["_odds"].where(df["_odds"] > 1, df[col["sp"]].map(parse_sp))
        df["_pos"] = df[col["pos"]].map(parse_pos)
        if col["race"]:
            key = df[col["race"]].astype(str)
        else:
            key = df["_date"].dt.strftime("%Y-%m-%d") + "|" + df[col["course"]].astype(str) + "|" + \
                (df[col["time"]].astype(str) if col["time"] else "")
        df["_key"] = key
        for k, g in df.groupby("_key", sort=False):
            odds = g["_odds"].tolist()
            if len(g) < MIN_RUNNERS or any(not (isinstance(o, float) and o > 1) for o in odds):
                continue
            pos = [None if pd.isna(p) else int(p) for p in g["_pos"].tolist()]
            if not any(p == 1 for p in pos):
                continue
            order = [i for i, _ in sorted(((i, p) for i, p in enumerate(pos) if p), key=lambda x: x[1])]
            title = str(g[col["title"]].iloc[0]) if col["title"] else ""
            first = g.iloc[0]
            out.append({
                "key": str(k),
                "date": first["_date"].strftime("%Y-%m-%d"),
                "course": str(first[col["course"]]) if col["course"] else "",
                "country": str(first[col["country"]]) if col["country"] else "",
                "handicap": "handicap" in title.lower() or "h'cap" in title.lower(),
                "runners": [{"name": str(h), "odds": float(o)} for h, o in zip(g[col["horse"]], odds)],
                "order": order,
                "finish": pos,
            })
    out.sort(key=lambda r: r["date"])
    return out
