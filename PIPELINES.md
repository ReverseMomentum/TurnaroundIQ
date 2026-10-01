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

### FTA model (V6 "path" model)

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

V6 additions (each kept only if it wins on held-back matches at train time):

- **Behaviour inputs** — late goals conceded / scored (76'+), points kept when
  leading, points and goals the opponent gets while behind, share of 2-ups
  before the hour. Need goal minutes: historical events, and live results from
  the `live_goals` table (filled by the results collector from now on).
- **Over/under 2.5** — de-margined market P(over); historical from
  football-data (`collectors/odds_history_fd.py`), live from the api-sports odds
  call. A separate model variant is used only when a fixture has O/U prices.
- **Calibration** — Platt scaling of the full-event FTA% fitted on walk-forward
  (out-of-sample) predictions. `walk-forward` prints raw vs calibrated bands,
  calibrating each fold only on earlier folds.
- **Recency weighting** — the FTA rate has drifted up (fail once 2-up ~7% in
  2016 to ~9% in 2026), so `train` also tries fitting with recent seasons
  weighted more (half-life 4y / 2y vs equal) on the held-back latest matches,
  and weights the calibration the same way if that predicts the latest
  walk-forward period better. The choice is stored in the bundle and reused by
  `walk-forward`, which also prints calibrated predicted vs actual per fold.

```bash
python -u run.py model-compare   # V5 inputs vs + behaviour vs + over/under, walk-forward
python -u run.py train           # picks the input set, calibrates, saves fta_path_model.pkl
python -u run.py walk-forward    # honest check of the trained input set
```

### Odds experiment (free historical odds)

```bash
python -u collectors/odds_history_fd.py          # football-data.co.uk -> match_odds (cached CSVs)
python -u models/fta_path_model.py odds-test     # same folds with vs without odds
```

Links each football-data row to an api-sports match by league + date (±1
day) + fuzzy names and prints the link rate per league. The test compares
AUC / top-10% lift with and without de-margined market odds on the same
matches. Odds are not used by the served model until a live odds feed exists.

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
