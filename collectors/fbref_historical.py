"""
FBref historical matches for the sample-weight window.

Half-life is 2 years; weight hits the 0.05 floor around 8.6 years.
Default first season is 2017-18.

What this stores
- historical_matches: date, teams, FT score
- team_stats.avg_xg / avg_xga when FBref shooting tables exist

What this does NOT store
- goal minutes / 2-up flags (that needs one HTML page per match;
  use --shots only for a single league/season or you will get blocked)

Usage:
    python -u collectors/fbref_historical.py
    python -u collectors/fbref_historical.py --league "Premier League" --season 2024
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db
from progress import ProgressBar, ok, step, warn
from team_normalizer import normalize_team

FIRST_SEASON = 2017

# soccerdata FBref keys -> our league names
FBREF_LEAGUES = {
    "ENG-Premier League": "Premier League",
    "ENG-Championship": "Championship",
    "ESP-La Liga": "La Liga",
    "GER-Bundesliga": "Bundesliga",
    "ITA-Serie A": "Serie A",
    "FRA-Ligue 1": "Ligue 1",
    "NED-Eredivisie": "Eredivisie",
    "POR-Primeira Liga": "Primeira Liga",
    "BEL-Jupiler Pro League": "Jupiler Pro League",
    "USA-Major League Soccer": "Major League Soccer",
}

SLEEP_SECONDS = 4.0


def season_list(start=FIRST_SEASON):
    import datetime
    last = datetime.datetime.utcnow().year
    return list(range(start, last + 1))


def _cell(row, *names):
    for name in names:
        if name in row and row[name] == row[name]:
            return row[name]
        for key in row.index:
            if str(key).lower() == name.lower():
                value = row[key]
                if value == value:
                    return value
    return None


def _to_int(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—"}:
        return None
    if "–" in text:
        parts = text.replace(" ", "").split("–")
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upsert_match(match_id, date, league, season, home, away, final_home, final_away):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO historical_matches (
            match_id, date, league, season, country,
            home_team, away_team, final_home, final_away
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
            date=excluded.date,
            league=excluded.league,
            season=excluded.season,
            home_team=excluded.home_team,
            away_team=excluded.away_team,
            final_home=excluded.final_home,
            final_away=excluded.final_away
        """,
        (match_id, date, league, str(season), home, away, final_home, final_away),
    )
    conn.commit()
    conn.close()


def bump_team_xg(team, xg, xga):
    if xg is None and xga is None:
        return
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
    conn.execute(
        """
        UPDATE team_stats
        SET
            avg_xg = CASE
                WHEN ? IS NULL THEN avg_xg
                WHEN avg_xg IS NULL THEN ?
                ELSE ROUND((avg_xg + ?) / 2.0, 3)
            END,
            avg_xga = CASE
                WHEN ? IS NULL THEN avg_xga
                WHEN avg_xga IS NULL THEN ?
                ELSE ROUND((avg_xga + ?) / 2.0, 3)
            END
        WHERE team = ?
        """,
        (xg, xg, xg, xga, xga, xga, team),
    )
    conn.commit()
    conn.close()


def ingest_schedule(frame, league_name, season):
    saved = 0
    if frame is None or frame.empty:
        return 0
    frame = frame.reset_index()
    bar = ProgressBar(len(frame), label=league_name[:12])
    for _, row in frame.iterrows():
        home = normalize_team(str(_cell(row, "home_team", "Home") or ""))
        away = normalize_team(str(_cell(row, "away_team", "Away") or ""))
        if not home or not away or home == "nan" or away == "nan":
            bar.update(detail="skip")
            continue
        date = str(_cell(row, "date", "Date") or "")[:10]
        score = _cell(row, "score", "Score")
        parsed = _to_int(score)
        if isinstance(parsed, tuple):
            final_home, final_away = parsed
        else:
            final_home = _to_int(_cell(row, "home_goals", "FTHG"))
            final_away = _to_int(_cell(row, "away_goals", "FTAG"))
        match_id = f"fbref-{league_name}-{date}-{home}-{away}"
        upsert_match(match_id, date, league_name, season, home, away, final_home, final_away)
        saved += 1
        bar.update(detail=f"{home} v {away}")
    bar.finish(detail=f"+{saved}")
    return saved


def ingest_shooting(frame, league_name):
    if frame is None or frame.empty:
        return 0
    frame = frame.reset_index()
    updated = 0
    for _, row in frame.iterrows():
        team = normalize_team(str(_cell(row, "team", "Squad") or ""))
        if not team or team == "nan":
            continue
        xg = _to_float(_cell(row, "xg", "xG"))
        xga = _to_float(_cell(row, "xga", "xGA"))
        if xg is None and xga is None:
            continue
        bump_team_xg(team, xg, xga)
        updated += 1
    return updated


def collect(leagues=None, seasons=None):
    try:
        import soccerdata as sd
    except ImportError:
        warn("Install soccerdata first: pip install soccerdata lxml")
        sys.exit(1)

    wanted = leagues or list(FBREF_LEAGUES.keys())
    years = seasons or season_list()
    jobs = [(key, year) for key in wanted for year in years]
    step(f"{len(jobs)} FBref league-seasons (sleep {SLEEP_SECONDS}s)")
    bar = ProgressBar(len(jobs), label="FBref")
    total_matches = 0
    total_xg = 0

    for key, year in jobs:
        league_name = FBREF_LEAGUES.get(key, key)
        label = f"{league_name} {year}"
        try:
            fbref = sd.FBref(leagues=key, seasons=year, no_cache=False)
            schedule = fbref.read_schedule()
            saved = ingest_schedule(schedule, league_name, year)
            total_matches += saved
            ok(f"{label}: {saved} matches")
            time.sleep(SLEEP_SECONDS)
            try:
                shooting = fbref.read_team_match_stats(stat_type="shooting")
                xg_rows = ingest_shooting(shooting, league_name)
                total_xg += xg_rows
                ok(f"{label}: {xg_rows} shooting rows")
            except Exception as exc:
                warn(f"{label} shooting skipped: {exc}")
            time.sleep(SLEEP_SECONDS)
        except Exception as exc:
            warn(f"{label} failed: {exc}")
        bar.update(detail=label)

    bar.finish()
    ok(f"historical_matches +{total_matches}")
    ok(f"team_stats xG touches {total_xg}")
    step("No goal minutes stored. FTA labels still come from results_collector.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", help="Our league name, e.g. Premier League")
    parser.add_argument("--season", type=int, help="Start year, e.g. 2024")
    args = parser.parse_args()
    leagues = None
    if args.league:
        matches = [k for k, v in FBREF_LEAGUES.items() if v.lower() == args.league.lower()]
        if not matches:
            warn(f"Unknown league {args.league}")
            warn("Options: " + ", ".join(sorted(set(FBREF_LEAGUES.values()))))
            sys.exit(1)
        leagues = matches
    seasons = [args.season] if args.season else None
    collect(leagues=leagues, seasons=seasons)


if __name__ == "__main__":
    main()
