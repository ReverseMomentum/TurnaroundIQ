"""
Runner features for the learned model, built point-in-time (only races before
the one being scored), the same way for training (Kaggle history) and live
(Betfair runner data + our own stored history).

Rates are shrunk towards a base rate so small samples do not shout:
    rate = (placed + m * base) / (runs + m)
"Placed" in history means finished in the first three.

Feature groups (the learner keeps a group only if it improves held-back fit):
  rating       or_rel, or_gap_top, or_missing
  weight_draw  weight_rel, draw_rel (flat only)
  freshness    log_days, first_run
  form         last_pos, avg3_pos, avg5_pos, form_missing
  suitability  course_rate, distance_rate, going_rate
  connections  jockey_rate, trainer_rate, jockey_30d, trainer_30d, horse_jockey_rate
  market       market_rank_pct
Logged only (not learned): speed ratings (no live source), race-wide values
(field_avg_or, race_depth, competitiveness: equal for every runner in a race,
so they cannot separate runners), matched volume (live only).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from racing import market, nonfinish

GROUPS = {
    "rating": ["or_rel", "or_gap_top", "or_missing"],
    "weight_draw": ["weight_rel", "draw_rel"],
    "freshness": ["log_days", "first_run"],
    "form": ["last_pos", "avg3_pos", "avg5_pos", "form_missing"],
    "suitability": ["course_rate", "distance_rate", "going_rate"],
    "connections": ["jockey_rate", "trainer_rate", "jockey_30d", "trainer_30d", "horse_jockey_rate"],
    "market": ["market_rank_pct"],
}
LOGGED_ONLY = ["last_speed", "avg3_speed", "avg5_speed", "field_avg_or", "race_depth", "competitiveness"]
BASE_PLACE = 0.30
SHRINK_HORSE = 4.0
SHRINK_PEOPLE = 30.0
NOT_FINISHED_POS = 12      # a fall / pull-up counts as a bad run in form averages
FORM_CAP = 10              # "0" in form strings = 10th or worse


def shrink(placed, runs, m, base=BASE_PLACE):
    runs = np.maximum(runs, 0)
    placed = np.clip(placed, 0, runs)
    return (placed + m * base) / (runs + m)


def going_group(text) -> str:
    t = str(text or "").lower()
    if "heavy" in t:
        return "heavy"
    if "soft" in t:
        return "soft"
    if "firm" in t or "hard" in t:
        return "firm"
    if "standard" in t or "slow" in t or "fast" in t:
        return "aw"
    if "good" in t:
        return "good"
    return "unknown"


def furlongs(text) -> Optional[int]:
    """'2m4f' / '1m 2f 110y' / 6 / '1408' (metres) -> whole furlongs."""
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return None
    if isinstance(text, (int, float)):
        x = float(text)
        return int(round(x / 201.17)) if x > 40 else int(round(x))
    s = str(text).lower().replace(" ", "")
    m = re.match(r"^(?:(\d+)m)?(?:(\d+)f)?(?:(\d+)y)?", s)
    if m and any(m.groups()):
        miles, fur, yards = (int(g) if g else 0 for g in m.groups())
        return int(round(miles * 8 + fur + yards / 220))
    try:
        return furlongs(float(s))
    except ValueError:
        return None


def parse_form(form: Optional[str]) -> list:
    """Betfair / RP form '1-3P20/4' -> recent positions, newest last (P/F/U.. -> 12, 0 -> 10)."""
    out = []
    for ch in str(form or ""):
        if ch.isdigit():
            out.append(FORM_CAP if ch == "0" else int(ch))
        elif ch.upper() in "PFURBSC":
            out.append(NOT_FINISHED_POS)
    return out


def form_features(positions: list) -> dict:
    if not positions:
        return {"last_pos": np.nan, "avg3_pos": np.nan, "avg5_pos": np.nan, "form_missing": 1.0}
    return {"last_pos": float(positions[-1]), "avg3_pos": float(np.mean(positions[-3:])),
            "avg5_pos": float(np.mean(positions[-5:])), "form_missing": 0.0}


def race_shape(p: np.ndarray) -> dict:
    p = np.asarray(p, float)
    n = len(p)
    ent = float(-(p * np.log(np.clip(p, 1e-12, 1))).sum() / math.log(n)) if n > 1 else 0.0
    return {"race_depth": ent, "competitiveness": float(np.sort(p)[::-1][:3].sum())}


def finish_race_features(rows: list[dict], odds: list) -> None:
    """Add within-race features in place (OR / weight relative, market rank, race shape)."""
    n = len(rows)
    ors = np.array([r.get("or") if r.get("or") else np.nan for r in rows], float)
    lbs = np.array([r.get("lbs") if r.get("lbs") else np.nan for r in rows], float)
    p = market.devig_power(odds) if all(o and o > 1 for o in odds) else np.full(n, 1.0 / n)
    rank = (-p).argsort().argsort()
    shape = race_shape(p)
    or_mean = np.nanmean(ors) if np.isfinite(ors).any() else np.nan
    or_top = np.nanmax(ors) if np.isfinite(ors).any() else np.nan
    lb_mean = np.nanmean(lbs) if np.isfinite(lbs).any() else np.nan
    for i, r in enumerate(rows):
        r["or_missing"] = 0.0 if np.isfinite(ors[i]) else 1.0
        r["or_rel"] = float(ors[i] - or_mean) if np.isfinite(ors[i]) else 0.0
        r["or_gap_top"] = float(or_top - ors[i]) if np.isfinite(ors[i]) else 0.0
        r["weight_rel"] = float(lbs[i] - lb_mean) if np.isfinite(lbs[i]) else 0.0
        d = r.get("draw")
        r["draw_rel"] = float(d) / n if (d and r.get("race_type") == "flat") else 0.0
        r["market_rank_pct"] = float(rank[i]) / max(1, n - 1)
        r["field_avg_or"] = float(or_mean) if np.isfinite(or_mean) else np.nan
        r.update(shape)


# ---- training: Kaggle hwaitt ------------------------------------------------

def _hwaitt_frame(paths: list[Path], years: Optional[tuple[int, int]]) -> pd.DataFrame:
    from racing.datasets import odds_from_price_column, parse_dates, parse_pos

    files = []
    for p in paths:
        files.extend(sorted(p.rglob("*")) if p.is_dir() else [p])
    races = {re.sub(r"\D", "", f.stem): f for f in files if f.name.lower().startswith("races_")}
    frames = []
    for f in files:
        if not f.name.lower().startswith("horses_") or f.suffix != ".csv":
            continue
        year = re.sub(r"\D", "", f.stem)
        if years and year and not (years[0] - 2 <= int(year) <= years[1]):   # 2 extra years of history
            continue
        h = pd.read_csv(f, low_memory=False)
        r = races.get(year)
        if r is None:
            continue
        rr = pd.read_csv(r, low_memory=False)
        keep = [c for c in ("rid", "course", "date", "title", "metric", "distance", "condition", "countryCode")
                if c in rr.columns]
        frames.append(h.merge(rr[keep], on="rid", how="left"))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["countryCode"].astype(str).str.upper().isin({"GB", "IE", "IRE", "UK"})] if "countryCode" in df else df
    df["date"] = parse_dates(df["date"])
    df = df[df["date"].notna()].copy()   # an unreadable date would break the date-ordered history
    df["odds"] = odds_from_price_column(df["decimalPrice"])
    df["pos"] = df["position"].map(parse_pos)
    df["lbs"] = pd.to_numeric(df.get("weightSt"), errors="coerce") * 14 + pd.to_numeric(df.get("weightLb"), errors="coerce")
    df["or"] = pd.to_numeric(df.get("OR"), errors="coerce")
    df["speed"] = pd.to_numeric(df.get("TR"), errors="coerce")
    df["draw"] = pd.to_numeric(df.get("saddle"), errors="coerce")
    df["dist_f"] = (df["metric"] if "metric" in df else df["distance"]).map(furlongs)
    df["going"] = df["condition"].map(going_group)
    df["race_type"] = df["title"].map(lambda t: nonfinish.race_type(t))
    df["placed"] = (df["pos"].fillna(99) <= 3).astype(float)
    df["form_pos"] = df["pos"].fillna(NOT_FINISHED_POS).clip(upper=NOT_FINISHED_POS)
    for col in ("horseName", "jockeyName", "trainerName", "course"):
        df[col] = df[col].fillna("?").astype(str)
    df = df.sort_values(["date", "rid"]).reset_index(drop=True)
    return df


def _prior_rate(df, keys, m):
    """Shrunk place rate from earlier rows of the same group (no look-ahead)."""
    g = df.groupby(keys, sort=False)["placed"]
    runs = g.cumcount()
    placed = g.cumsum() - df["placed"]
    return shrink(placed, runs, m)


def _rolling_30d(df, key):
    """Shrunk place rate over the previous 30 days (same day excluded). df is sorted by date."""
    out = np.empty(len(df))
    days = df["date"].values.astype("datetime64[D]").astype(np.int64)
    placed = df["placed"].values
    for idx in df.groupby(key, sort=False).indices.values():
        d, pl = days[idx], placed[idx]
        cum = np.concatenate([[0.0], np.cumsum(pl)])
        lo = np.searchsorted(d, d - 30, side="left")    # first run inside the window
        hi = np.searchsorted(d, d, side="left")         # stop before today's runs
        out[idx] = shrink(cum[hi] - cum[lo], hi - lo, SHRINK_PEOPLE / 3)
    return pd.Series(out, index=df.index)


def training_features(paths: list[Path], years: Optional[tuple[int, int]] = None) -> dict:
    """{(race key, horse): features} for Kaggle hwaitt files, point-in-time."""
    df = _hwaitt_frame(paths, years)
    if df.empty:
        return {}
    h = df.groupby("horseName", sort=False)
    df["first_run"] = (h.cumcount() == 0).astype(float)
    df["log_days"] = np.log1p((df["date"] - h["date"].shift()).dt.days.clip(lower=0)).fillna(0.0)
    for k, name in ((1, "last_pos"), (3, "avg3_pos"), (5, "avg5_pos")):
        df[name] = h["form_pos"].transform(lambda s, k=k: s.shift().rolling(k, min_periods=1).mean())
    df["form_missing"] = df["last_pos"].isna().astype(float)
    for k, name in ((1, "last_speed"), (3, "avg3_speed"), (5, "avg5_speed")):
        df[name] = h["speed"].transform(lambda s, k=k: s.shift().rolling(k, min_periods=1).mean())
    df["course_rate"] = _prior_rate(df, ["horseName", "course"], SHRINK_HORSE)
    df["dist_bucket"] = df["dist_f"].fillna(-1)
    df["distance_rate"] = _prior_rate(df, ["horseName", "dist_bucket"], SHRINK_HORSE)
    df["going_rate"] = _prior_rate(df, ["horseName", "going"], SHRINK_HORSE)
    df["jockey_rate"] = _prior_rate(df, ["jockeyName"], SHRINK_PEOPLE)
    df["trainer_rate"] = _prior_rate(df, ["trainerName"], SHRINK_PEOPLE)
    df["horse_jockey_rate"] = _prior_rate(df, ["horseName", "jockeyName"], SHRINK_HORSE)
    df["jockey_30d"] = _rolling_30d(df, "jockeyName")
    df["trainer_30d"] = _rolling_30d(df, "trainerName")
    if years:
        df = df[(df["date"].dt.year >= years[0]) & (df["date"].dt.year <= years[1])]
    out = {}
    for rid, g in df.groupby("rid", sort=False):
        rows = g.to_dict("records")
        finish_race_features(rows, list(g["odds"]))
        for r in rows:
            out[(str(rid), str(r["horseName"]))] = {k: _clean(r.get(k)) for k in all_names()}
    return out


def _clean(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def all_names() -> list:
    return [f for g in GROUPS.values() for f in g] + LOGGED_ONLY


def attach(races: list[dict], feats: dict) -> int:
    """Put features on datasets.load_races runners (matched by race key + horse name)."""
    n = 0
    for race in races:
        for r in race["runners"]:
            f = feats.get((race["key"], r["name"]))
            if f is not None:
                r["features"] = f
                n += 1
    return n
