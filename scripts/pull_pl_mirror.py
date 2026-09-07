#!/usr/bin/env python3
"""Pull Premier League results from the AnishKhetani GitHub mirror.

Source: https://github.com/AnishKhetani/premier-league-data
Upstream origin: football-data.co.uk (no live scrape of that site).

Does NOT include xG or possession. Those need FBref/Understat/Sofascore.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

MIRROR_RESULTS = (
    "https://raw.githubusercontent.com/AnishKhetani/premier-league-data/"
    "main/data/processed/results.csv"
)
MIRROR_ODDS = (
    "https://raw.githubusercontent.com/AnishKhetani/premier-league-data/"
    "main/data/processed/results_with_odds.csv"
)

DEFAULT_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def pull(seasons: list[str], with_odds: bool, out: Path) -> pd.DataFrame:
    url = MIRROR_ODDS if with_odds else MIRROR_RESULTS
    df = pd.read_csv(url)
    if seasons:
        df = df[df["season"].astype(str).isin(seasons)].copy()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS)
    p.add_argument("--odds", action="store_true")
    p.add_argument("--out", default="stats/prem_results_github_mirror.csv")
    args = p.parse_args()
    df = pull(args.seasons, args.odds, Path(args.out))
    print(f"wrote {len(df)} rows -> {args.out}")
    print(df.groupby("season").size().to_string())


if __name__ == "__main__":
    main()
