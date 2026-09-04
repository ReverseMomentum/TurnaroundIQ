"""
FBref historical pipeline with 2-up / turnaround labels.

1. Pull the season schedule (FT score -> historical_matches).
2. Pull each match shooting table (goal minutes -> historical_events).
3. Replay the scoreline and write match_results 2-up / FTA flags.

Default window is 2017-18 onward (decay floor ~8.6 years).

FBref will ban a full 10-league scrape in one sitting. Run one
league-season at a time. Re-runs skip matches that already have events.

    python -u collectors/fbref_historical.py --league "Premier League" --season 2024
    python -u collectors/fbref_historical.py --league "Premier League" --season 2024 --skip-shots
"""

import argparse
import re
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database import get_db
from progress import ProgressBar, ok, step, warn
from team_normalizer import normalize_team

FIRST_SEASON = 2017
SLEEP_SECONDS = 5.0
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TurnaroundIQ/1.0; "
        "historical research; +https://github.com/ReverseMomentum/TurnaroundIQ)"
    )
}

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


def season_list(start=FIRST_SEASON):
    import datetime
    return list(range(start, datetime.datetime.utcnow().year + 1))


def _cell(row, *names):
    for name in names:
        if name in getattr(row, "index", []):
            value = row[name]
            if value == value:
                return value
        for key in getattr(row, "index", []):
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


def match_id_for(league, date, home, away):
    return f"fbref-{league}-{date}-{home}-{away}"


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


def has_events(match_id):
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM historical_events WHERE match_id = ? LIMIT 1",
        (match_id,),
    ).fetchone()
    conn.close()
    return row is not None


def save_goal_event(match_id, minute, team, player):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO historical_events (
            match_id, minute, event_type, event_type2, side,
            team, player, is_goal, situation
        )
        VALUES (?, ?, 1, NULL, NULL, ?, ?, 1, NULL)
        """,
        (match_id, minute, team, player),
    )
    conn.commit()
    conn.close()


def save_match_result(match_id, league, home, away, final_home, final_away, flags):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO match_results (
            match_id, league, home_team, away_team,
            final_home, final_away,
            home_2up, away_2up,
            home_turnaround, away_turnaround,
            home_lead_minute, away_lead_minute,
            processed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            match_id, league, home, away,
            final_home, final_away,
            flags["home_2up"], flags["away_2up"],
            flags["home_turnaround"], flags["away_turnaround"],
            flags["home_lead_minute"], flags["away_lead_minute"],
        ),
    )
    conn.commit()
    conn.close()


def replay_two_up(goals, home, away, final_home, final_away):
    home_goals = 0
    away_goals = 0
    home_2up = 0
    away_2up = 0
    home_lead_minute = None
    away_lead_minute = None
    for minute, team, _player in goals:
        if team == home:
            home_goals += 1
        elif team == away:
            away_goals += 1
        if home_goals - away_goals >= 2:
            home_2up = 1
        if away_goals - home_goals >= 2:
            away_2up = 1
        if home_goals > away_goals and home_lead_minute is None:
            home_lead_minute = minute
        if away_goals > home_goals and away_lead_minute is None:
            away_lead_minute = minute
    home_turnaround = int(away_2up == 1 and (final_home or 0) > (final_away or 0))
    away_turnaround = int(home_2up == 1 and (final_away or 0) > (final_home or 0))
    return {
        "home_2up": home_2up,
        "away_2up": away_2up,
        "home_turnaround": home_turnaround,
        "away_turnaround": away_turnaround,
        "home_lead_minute": home_lead_minute,
        "away_lead_minute": away_lead_minute,
    }


def parse_minute(raw):
    if raw is None:
        return None
    text = str(raw).strip()
    match = re.match(r"(\d+)", text)
    if not match:
        return None
    minute = int(match.group(1))
    extra = re.search(r"\+(\d+)", text)
    if extra:
        minute += int(extra.group(1))
    return minute


def goals_from_html(html, home, away):
    import pandas as pd

    tables = pd.read_html(html)
    goals = []
    for table in tables:
        cols = [str(c).lower() for c in table.columns]
        joined = " ".join(cols)
        if "minute" not in joined:
            continue
        minute_col = next((c for c in table.columns if "min" in str(c).lower()), None)
        team_col = next(
            (c for c in table.columns if str(c).lower() in {"squad", "team"}),
            None,
        )
        outcome_col = next(
            (c for c in table.columns if "outcome" in str(c).lower() or "result" in str(c).lower()),
            None,
        )
        player_col = next(
            (c for c in table.columns if "player" in str(c).lower()),
            None,
        )
        if minute_col is None or team_col is None:
            continue
        for _, row in table.iterrows():
            outcome = str(row[outcome_col]).lower() if outcome_col is not None else ""
            # Shot tables mark goals; some event tables already are goals only.
            if outcome and "goal" not in outcome and "own" not in outcome:
                continue
            minute = parse_minute(row[minute_col])
            team = normalize_team(str(row[team_col]))
            if minute is None or team not in {home, away}:
                continue
            player = str(row[player_col]) if player_col is not None else ""
            goals.append((minute, team, player))
        if goals:
            break
    goals.sort(key=lambda item: item[0])
    return goals


def fetch_match_html(url):
    response = requests.get(url, headers=HEADERS, timeout=45)
    if response.status_code == 429:
        raise RuntimeError("FBref rate limited (429). Stop and retry tomorrow.")
    response.raise_for_status()
    return response.text


def extract_url(row):
    for name in ("url", "match_url", "game_url", "href"):
        value = _cell(row, name)
        if value and str(value).startswith("http"):
            return str(value)
    for key in getattr(row, "index", []):
        value = row[key]
        text = str(value)
        if "fbref.com/en/matches/" in text:
            return text if text.startswith("http") else "https://fbref.com" + text
    return None


def ingest_shots_for_row(row, league_name, season, home, away, date, final_home, final_away):
    match_id = match_id_for(league_name, date, home, away)
    if has_events(match_id):
        return "skip"
    url = extract_url(row)
    if not url:
        return "nourl"
    html = fetch_match_html(url)
    goals = goals_from_html(html, home, away)
    for minute, team, player in goals:
        save_goal_event(match_id, minute, team, player)
    flags = replay_two_up(goals, home, away, final_home, final_away)
    save_match_result(match_id, league_name, home, away, final_home, final_away, flags)
    return f"{len(goals)}g 2up={flags['home_2up']}/{flags['away_2up']} fta={flags['home_turnaround']}/{flags['away_turnaround']}"


def ingest_schedule(frame, league_name, season, with_shots):
    saved = 0
    shot_ok = 0
    if frame is None or getattr(frame, "empty", True):
        return 0, 0
    frame = frame.reset_index()
    bar = ProgressBar(len(frame), label=league_name[:12])
    for _, row in frame.iterrows():
        home = normalize_team(str(_cell(row, "home_team", "Home") or ""))
        away = normalize_team(str(_cell(row, "away_team", "Away") or ""))
        if not home or not away or home == "nan":
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
        match_id = match_id_for(league_name, date, home, away)
        upsert_match(match_id, date, league_name, season, home, away, final_home, final_away)
        saved += 1
        detail = f"{home} v {away}"
        if with_shots:
            try:
                status = ingest_shots_for_row(
                    row, league_name, season, home, away, date, final_home, final_away
                )
                if status not in {"skip", "nourl"}:
                    shot_ok += 1
                    time.sleep(SLEEP_SECONDS)
                detail = f"{home} {status}"
            except Exception as exc:
                warn(f"{home} v {away}: {exc}")
                if "429" in str(exc):
                    raise
                time.sleep(SLEEP_SECONDS)
        bar.update(detail=detail)
    bar.finish(detail=f"+{saved} matches, {shot_ok} shot pages")
    return saved, shot_ok


def collect(leagues=None, seasons=None, with_shots=True):
    try:
        import soccerdata as sd
    except ImportError:
        warn("pip install soccerdata lxml")
        sys.exit(1)

    wanted = leagues or list(FBREF_LEAGUES.keys())
    years = seasons or season_list()
    jobs = [(key, year) for key in wanted for year in years]
    step(f"{len(jobs)} league-seasons | shots={'on' if with_shots else 'off'}")
    bar = ProgressBar(len(jobs), label="FBref")
    total_matches = 0
    total_shot_pages = 0

    for key, year in jobs:
        league_name = FBREF_LEAGUES.get(key, key)
        label = f"{league_name} {year}"
        try:
            fbref = sd.FBref(leagues=key, seasons=year, no_cache=False)
            schedule = fbref.read_schedule()
            saved, shot_ok = ingest_schedule(schedule, league_name, year, with_shots)
            total_matches += saved
            total_shot_pages += shot_ok
            ok(f"{label}: {saved} matches, {shot_ok} timelines")
            time.sleep(SLEEP_SECONDS)
        except Exception as exc:
            warn(f"{label} failed: {exc}")
            if "429" in str(exc):
                warn("Stop here. Re-run the same command tomorrow; finished matches are saved.")
                break
        bar.update(detail=label)
    bar.finish()
    ok(f"historical_matches +{total_matches}")
    ok(f"shot timelines +{total_shot_pages}")
    step("Rebuild team profiles + training_data after a season finishes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", help='e.g. "Premier League"')
    parser.add_argument("--season", type=int, help="Start year, e.g. 2024")
    parser.add_argument("--skip-shots", action="store_true", help="Scores only, no 2-up")
    args = parser.parse_args()
    leagues = None
    if args.league:
        matches = [k for k, v in FBREF_LEAGUES.items() if v.lower() == args.league.lower()]
        if not matches:
            warn("Unknown league. " + ", ".join(sorted(set(FBREF_LEAGUES.values()))))
            sys.exit(1)
        leagues = matches
    seasons = [args.season] if args.season else None
    collect(leagues=leagues, seasons=seasons, with_shots=not args.skip_shots)


if __name__ == "__main__":
    main()
