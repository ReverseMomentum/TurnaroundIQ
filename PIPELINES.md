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
| `historical` | backup → import `data/ginf.csv` + `data/events.csv` → historical profiles |
| `train` | backup → build `training_data` → retrain model (refuses on empty rows) |
| `backup` | dated copy of `two_up.db` in `backups/` |
| `health` | row counts, freshness, backup age; exit 0/1/2 |

Secrets come from `/etc/turnaroundiq.env` or `.env` (see `deploy/env.example`).
Scheduling, restore and incident steps: `deploy/RUNBOOK.md`.
Tests: `python -m pytest tests -q`.

Old layout: branch `backup/pre-tidy`.
