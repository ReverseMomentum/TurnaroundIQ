"""
Historical pipeline — TheStatsAPI (default) or FBref -> CSVs ->
historical_* tables -> team_stats profiles.

    python -u run.py historical                                   # TheStatsAPI, all leagues, resumes
    python -u run.py historical --league "Premier League" --season 2024
    python -u run.py historical --max-matches 800                 # cap API calls this run
    python -u run.py historical --no-fetch                        # rebuild from existing CSVs only
    python -u run.py historical --only-thestatsapi                # ignore legacy FBref CSVs
    python -u run.py historical --source fbref --fetch            # legacy FBref scrape

TheStatsAPI collection is resumable: if the daily quota runs out the pipeline
still rebuilds profiles from everything collected so far, and the next run
continues where this one stopped.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from progress import ok, step, warn
from ops.backup import BackupError, backup_db

GINF = ROOT / "data" / "ginf.csv"
EVENTS = ROOT / "data" / "events.csv"
GINF_API = ROOT / "data" / "ginf_api.csv"
BACKFILL_PARTIAL = 3  # collectors/backfill_thestatsapi.py stopped early


def run_script(script, extra=None, allowed=(0,)):
    cmd = [sys.executable, "-u", str(ROOT / script)]
    if extra:
        cmd.extend(extra)
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode not in allowed:
        raise SystemExit(result.returncode)
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["thestatsapi", "fbref"], default="thestatsapi")
    parser.add_argument("--fetch", action="store_true", help="FBref: scrape even if CSVs exist")
    parser.add_argument("--no-fetch", action="store_true", help="Skip collection; rebuild from CSVs")
    parser.add_argument("--league")
    parser.add_argument("--season", type=int)
    parser.add_argument("--max-matches", type=int, default=0,
                        help="TheStatsAPI: cap timelines fetched this run")
    parser.add_argument("--only-thestatsapi", action="store_true",
                        help="Import TheStatsAPI CSVs only (ignore legacy FBref CSVs)")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Accept a smaller historical_matches than today's")
    args = parser.parse_args()

    started = time.time()
    if args.no_fetch:
        step("Skipping collection (--no-fetch)")
    elif args.source == "thestatsapi":
        extra = []
        if args.league:
            extra += ["--league", args.league]
        if args.season:
            extra += ["--year", str(args.season)]
        if args.max_matches:
            extra += ["--max-matches", str(args.max_matches)]
        step("Collect historical matches from TheStatsAPI")
        code = run_script(
            "collectors/backfill_thestatsapi.py", extra,
            allowed=(0, BACKFILL_PARTIAL),
        )
        if code == BACKFILL_PARTIAL:
            warn("TheStatsAPI collection incomplete — rebuilding from what we have; rerun to continue")
    elif args.fetch or not GINF.exists() or not EVENTS.exists():
        extra = []
        if args.league:
            extra += ["--league", args.league]
        if args.season:
            extra += ["--season", str(args.season)]
        step("Fetch FBref source CSVs")
        run_script("training/fetch_fbref_source.py", extra)
    else:
        step("Using existing data/ginf.csv and data/events.csv")

    if args.only_thestatsapi or args.source == "thestatsapi" and not GINF.exists():
        import_source = "thestatsapi"
    elif args.source == "fbref" and not GINF_API.exists():
        import_source = "fbref"
    else:
        import_source = "all"
    if import_source != "fbref" and not GINF_API.exists():
        warn("data/ginf_api.csv not found — nothing collected from TheStatsAPI yet")
        raise SystemExit(1)

    step("Back up two_up.db")
    try:
        backup_db("pre-historical")
    except BackupError as exc:
        warn(f"Backup failed ({exc}) — not importing without a backup")
        raise SystemExit(1)

    step(f"Import historical events (source: {import_source})")
    import_args = ["--source", import_source]
    if args.allow_shrink:
        import_args.append("--allow-shrink")
    code = run_script("training/import_historical_events.py", import_args, allowed=(0, 4))
    if code == 4:
        warn("Import skipped: new data smaller than current — profiles left as they were")
        raise SystemExit(4)

    step("Build historical team profiles")
    run_script("pipelines/historical/build.py")

    ok(f"Historical pipeline {round(time.time() - started, 1)}s")


if __name__ == "__main__":
    main()
