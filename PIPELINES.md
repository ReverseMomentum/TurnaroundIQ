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
| `train` | backup → fit the FTA path model (`fta_path_model.pkl`) |
| `walk-forward` | train on the past, test on later seasons; honest accuracy vs a flat-rate baseline |
| `backup` | dated copy of `two_up.db` in `backups/` |
| `health` | row counts, freshness, backup age; exit 0/1/2 |

### FTA model (V5 "path" model)

FTA% served to the app is the **full event**: the team goes 2 goals up **and**
fails to win. It is the product of two models:

- P(2-up) — trained on every team in every match
- P(fail to win | 2-up) — trained on teams that went 2 up

Features are built **point-in-time**: each match only sees results before it
(decayed, shrunk to the league average), including the team's usual 2-up
minute. Responses also carry `two_up_pct`, `fail_given_2up_pct`,
`usual_2up_minute` and `confidence` (= how much history backs the pick,
0–100, not a probability). Bands: `elite_4plus`, `high_3_4`, `mid_2_3`,
`low_1_2`, `micro_under_1`. The old conditional model is still available via
`run.py train --legacy` / `models/walk_forward.py`.

### Current season (live results)

```bash
python -u collectors/results_collector.py --season-to-date   # fill the season so far, all leagues
python -u run.py live                                         # daily: last RESULTS_LOOKBACK_DAYS days
```

Both fetch match events 20 fixtures per call and skip fixtures already
processed. Each result stores its kick-off date (`match_results.match_date`),
which form and training use for ordering.

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
