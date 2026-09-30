# How to run

```bash
python -u run.py live
python -u run.py historical
python -u run.py train
python -u run.py backup | backup --list | restore <file>
python -u run.py health
```

| Command | What it does |
|---|---|
| `live` | results → team_stats → football-data odds; backup after success |
| `historical` | collect from api-sports.io (resumable) → backup → import → historical profiles |
| `train` | backup → build `training_data` → retrain model (refuses on empty rows) |
| `backup` | dated copy of `two_up.db` in `backups/` |
| `health` | row counts, freshness, backup age; exit 0/1/2 |

### Historical data (api-sports.io)

```bash
python -u collectors/backfill_apisports.py --probe        # check key + parser on one league
python -u run.py historical --league-id 39 --season 2024  # small trial
python -u run.py historical                               # all leagues, last 5 completed seasons, resumes
python -u run.py historical --no-fetch                    # rebuild profiles from collected CSVs
python -u run.py historical --source fbref --fetch        # legacy FBref scrape
```

Leagues come from `SUPPORTED_LEAGUE_IDS` in `constants.py`. Nothing is fetched
twice: completed seasons are recorded in `data/apisports_done.csv`, stored
fixtures are never re-requested, and season lists are cached for 7 days — once
complete, the nightly run costs 0 calls. The in-progress season comes from the
live results collector (`--include-current` to backfill it too). Collected rows go
to `data/ginf_apisports.csv` / `data/events_apisports.csv`. Events come in
batches of 20 fixtures per call. A match is kept only if its goal events
reproduce the official score (missed penalties ignored, own goals resolved);
others are logged to `data/apisports_skipped.csv`. Older CSVs (`ginf_api.csv`,
FBref `ginf.csv`) only fill fixtures api-sports doesn't have
(`--only-apisports` to ignore them). The import refuses to shrink
`historical_matches` below 80% of its current size (`--allow-shrink`).

Secrets come from `/etc/turnaroundiq.env` or `.env` (see `deploy/env.example`).
Scheduling, restore and incident steps: `deploy/RUNBOOK.md`.
Tests: `python -m pytest tests -q`.

Old layout: branch `backup/pre-tidy`.
