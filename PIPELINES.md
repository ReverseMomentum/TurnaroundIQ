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
| `historical` | collect from TheStatsAPI (resumable) → backup → import → historical profiles |
| `train` | backup → build `training_data` → retrain model (refuses on empty rows) |
| `backup` | dated copy of `two_up.db` in `backups/` |
| `health` | row counts, freshness, backup age; exit 0/1/2 |

### Historical data (TheStatsAPI)

```bash
python -u collectors/backfill_thestatsapi.py --probe      # first run with a new key: check field names
python -u run.py historical --league "Premier League" --season 2024 --max-matches 400   # small trial
python -u run.py historical                               # all leagues 2020 → now, resumes each run
python -u run.py historical --no-fetch                    # rebuild profiles from collected CSVs
python -u run.py historical --source fbref --fetch        # legacy FBref scrape
```

Collected rows go to `data/ginf_api.csv` / `data/events_api.csv`. Matches whose
goal timeline doesn't add up to the final score are logged to
`data/thestatsapi_skipped.csv` instead of being imported. Legacy FBref CSVs, if
present, only fill fixtures TheStatsAPI doesn't have (`--only-thestatsapi` to
ignore them). The import refuses to shrink `historical_matches` below 80% of
its current size (`--allow-shrink` to override).

Secrets come from `/etc/turnaroundiq.env` or `.env` (see `deploy/env.example`).
Scheduling, restore and incident steps: `deploy/RUNBOOK.md`.
Tests: `python -m pytest tests -q`.

Old layout: branch `backup/pre-tidy`.
