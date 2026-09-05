# How to run

```bash
python -u run.py live
python -u run.py historical
python -u run.py train
```

| Command | What it does |
|---|---|
| `live` | results → team_stats → football-data odds |
| `historical` | import `data/ginf.csv` + `data/events.csv` → historical profiles |
| `train` | build `training_data` → retrain model |

Old layout: branch `backup/pre-tidy`.
