"""
Historical pipeline — api-sports.io backfill -> CSVs -> historical_* tables
-> team_stats profiles.

    python -u run.py historical                           # all leagues, 5 seasons + current, resumes
    python -u run.py historical --league-id 39 --season 2024
    python -u run.py historical --no-fetch                # rebuild from collected CSVs only
    python -u run.py historical --only-apisports          # ignore older CSVs (FBref / one-off backfills)
    python -u run.py historical --source fbref --fetch    # legacy FBref scrape

Collection is resumable: when the daily api-sports quota (minus the reserve
kept for live collection) runs out, the pipeline still rebuilds profiles from
everything collected so far, and the next run continues where it stopped.
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

DATA = ROOT / "data"
GINF_FBREF = DATA / "ginf.csv"
EVENTS_FBREF = DATA / "events.csv"
GINF_APISPORTS = DATA / "ginf_apisports.csv"
BACKFILL_PARTIAL = 3  # collectors/backfill_apisports.py stopped at the quota
IMPORT_SHRINK = 4     # training/import_historical_events.py refused to shrink


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
    parser.add_argument("--source", choices=["apisports", "fbref"], default="apisports")
    parser.add_argument("--fetch", action="store_true", help="FBref: scrape even if CSVs exist")
    parser.add_argument("--no-fetch", action="store_true", help="Skip collection; rebuild from CSVs")
    parser.add_argument("--league-id", type=int, action="append")
    parser.add_argument("--season", type=int, action="append")
    parser.add_argument("--seasons", type=int, help="Completed seasons per league (default 5)")
    parser.add_argument("--only-apisports", action="store_true",
                        help="Import api-sports CSVs only")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Accept a smaller historical_matches than today's")
    # FBref-only options
    parser.add_argument("--league")
    args = parser.parse_args()

    started = time.time()
    if args.no_fetch:
        step("Skipping collection (--no-fetch)")
    elif args.source == "apisports":
        extra = []
        for lid in args.league_id or []:
            extra += ["--league-id", str(lid)]
        for season in args.season or []:
            extra += ["--season", str(season)]
        if args.seasons:
            extra += ["--seasons", str(args.seasons)]
        step("Collect historical matches from api-sports.io")
        code = run_script("collectors/backfill_apisports.py", extra, allowed=(0, BACKFILL_PARTIAL))
        if code == BACKFILL_PARTIAL:
            warn("Daily quota reached — rebuilding from what we have; next run continues")
    elif args.fetch or not GINF_FBREF.exists() or not EVENTS_FBREF.exists():
        extra = []
        if args.league:
            extra += ["--league", args.league]
        if args.season:
            extra += ["--season", str(args.season[0])]
        step("Fetch FBref source CSVs")
        run_script("training/fetch_fbref_source.py", extra)
    else:
        step("Using existing data/ginf.csv and data/events.csv")

    if args.only_apisports:
        import_source = "apisports"
    elif args.source == "fbref":
        import_source = "fbref"
    else:
        import_source = "all"
    if import_source == "apisports" and not GINF_APISPORTS.exists():
        warn("data/ginf_apisports.csv not found — nothing collected from api-sports yet")
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
    code = run_script("training/import_historical_events.py", import_args,
                      allowed=(0, IMPORT_SHRINK))
    if code == IMPORT_SHRINK:
        warn("Import skipped: collected data smaller than current — profiles left as they were")
        raise SystemExit(IMPORT_SHRINK)

    step("Build historical team profiles")
    run_script("pipelines/historical/build.py")

    ok(f"Historical pipeline {round(time.time() - started, 1)}s")


if __name__ == "__main__":
    main()
