# Pipelines

Pre-tidy copy: branch `backup/pre-tidy`.

```bash
git fetch
git checkout backup/pre-tidy   # restore old layout
git checkout main
```

## Daily / live

```bash
python -u pipelines/live/run.py
python -u pipelines/live/run.py --skip-odds --skip-xg
```

1. `collectors/results_collector.py` → `match_results`
2. `pipelines/live/team_stats.py` → live 2-up rates
3. `training/update_live_team_stats.py` → form / divergence
4. xG + odds collectors

## Historical

```bash
python -u pipelines/historical/run.py
python -u pipelines/historical/run.py --fetch --league "Premier League" --season 2024
```

1. Optional FBref → `data/ginf.csv` + `data/events.csv`
2. `training/import_historical_events.py` → `historical_matches` / `historical_events`
3. `pipelines/historical/build.py` → `team_stats` historical_* columns

## Train

```bash
python -u pipelines/training/run.py
```

1. `training/build_training_data.py`
2. `models/retrain_model.py`

Old commands still work as shims: `python refresh_live.py`, `python setup_historical_data.py`.
