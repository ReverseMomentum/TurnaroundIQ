import time
from datetime import datetime, timedelta, timezone
import sqlite3
import requests

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from constants import API_FOOTBALL_KEY, SUPPORTED_LEAGUE_IDS
from team_normalizer import normalize_team

DB_NAME = "two_up.db"
LOOKBACK_DAYS = 2
REQUEST_DELAY = 3
EARLY_GOAL_CUTOFF = 30
HALF_CUTOFF = 45

HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

MATCH_RESULT_COLUMNS = {
    "match_id": "TEXT",
    "league": "TEXT",
    "home_team": "TEXT",
    "away_team": "TEXT",
    "final_home": "INTEGER",
    "final_away": "INTEGER",
    "home_2up": "INTEGER",
    "away_2up": "INTEGER",
    "home_turnaround": "INTEGER",
    "away_turnaround": "INTEGER",
    "home_lead_minute": "INTEGER",
    "away_lead_minute": "INTEGER",
    "home_early_goal": "INTEGER",
    "home_early_concede": "INTEGER",
    "away_early_goal": "INTEGER",
    "away_early_concede": "INTEGER",
    "home_first_lead": "INTEGER",
    "home_first_concede": "INTEGER",
    "away_first_lead": "INTEGER",
    "away_first_concede": "INTEGER",
    "home_led": "INTEGER",
    "away_led": "INTEGER",
    "home_first_half_for": "INTEGER",
    "home_first_half_against": "INTEGER",
    "home_second_half_for": "INTEGER",
    "home_second_half_against": "INTEGER",
    "away_first_half_for": "INTEGER",
    "away_first_half_against": "INTEGER",
    "away_second_half_for": "INTEGER",
    "away_second_half_against": "INTEGER",
    "processed_at": "TEXT",
}


def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def migrate_match_results():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT,
            league TEXT,
            home_team TEXT,
            away_team TEXT,
            final_home INTEGER,
            final_away INTEGER,
            home_2up INTEGER,
            away_2up INTEGER,
            home_turnaround INTEGER,
            away_turnaround INTEGER,
            processed_at TEXT
        )
        """
    )
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(match_results)").fetchall()
    }
    for name, typ in MATCH_RESULT_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE match_results ADD COLUMN {name} {typ}")
            print(f"Added match_results.{name}")
    conn.commit()
    conn.close()


def create_processed_fixtures_table():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_fixtures (
            fixture_id TEXT PRIMARY KEY,
            processed_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def fixture_already_processed(fixture_id):
    conn = get_db()
    row = conn.execute(
        "SELECT fixture_id FROM processed_fixtures WHERE fixture_id = ?",
        (str(fixture_id),),
    ).fetchone()
    conn.close()
    return row is not None


def mark_fixture_processed(fixture_id):
    conn = get_db()
    conn.execute(
        """
        INSERT OR REPLACE INTO processed_fixtures (fixture_id, processed_at)
        VALUES (?, ?)
        """,
        (str(fixture_id), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def update_form_from_results():
    """
    Fields xg_collector used to write that we can rebuild from scores.
    Does not write avg_xg / avg_xga / xg_edge — those need the xG API.
    Same last-5 sum as xg_collector (values['goals'][-5:]).
    """
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS team_stats (team TEXT PRIMARY KEY)")
    for col, typ in (
        ("goals_last5", "INTEGER"),
        ("conceded_last5", "INTEGER"),
        ("matches_played", "INTEGER"),
        ("updated_at", "TEXT"),
    ):
        existing = {row[1] for row in conn.execute("PRAGMA table_info(team_stats)")}
        if col not in existing:
            conn.execute(f"ALTER TABLE team_stats ADD COLUMN {col} {typ}")
    teams = conn.execute(
        """
        SELECT DISTINCT home_team FROM match_results
        UNION
        SELECT DISTINCT away_team FROM match_results
        """
    ).fetchall()
    updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for (team,) in teams:
        if not team:
            continue
        rows = conn.execute(
            """
            SELECT processed_at, final_home, final_away FROM match_results
            WHERE home_team = ?
            UNION ALL
            SELECT processed_at, final_away, final_home FROM match_results
            WHERE away_team = ?
            ORDER BY processed_at DESC
            """,
            (team, team),
        ).fetchall()
        matches_played = len(rows)
        last5 = rows[:5]
        goals_last5 = sum((row[1] or 0) for row in last5)
        conceded_last5 = sum((row[2] or 0) for row in last5)
        conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
        conn.execute(
            """
            UPDATE team_stats SET
                goals_last5 = ?,
                conceded_last5 = ?,
                matches_played = ?,
                updated_at = ?
            WHERE team = ?
            """,
            (goals_last5, conceded_last5, matches_played, now, team),
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"{updated} teams updated with last-5 goals from match_results")


def get_completed_fixtures():
    fixtures = []
    for day in range(LOOKBACK_DAYS):
        target_date = (
            datetime.now(timezone.utc) - timedelta(days=day)
        ).strftime("%Y-%m-%d")
        url = (
            "https://v3.football.api-sports.io/"
            f"fixtures?date={target_date}&status=FT"
        )
        try:
            response = requests.get(url, headers=HEADERS, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            print(f"API request failed: {exc}")
            continue
        day_fixtures = response.json().get("response", [])
        print(f"{target_date}: {len(day_fixtures)} fixtures")
        fixtures.extend(day_fixtures)
    print(f"Fixtures found: {len(fixtures)}")
    return fixtures


def get_fixture_events(fixture_id, max_retries=3):
    url = (
        "https://v3.football.api-sports.io/"
        f"fixtures/events?fixture={fixture_id}"
    )
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            if response.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"[RATE LIMIT] fixture {fixture_id} - sleeping {wait}s")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json().get("response", [])
        except Exception as exc:
            print(f"[EVENTS ERROR] fixture {fixture_id}: {exc}")
            time.sleep(2)
    print(f"[EVENTS FAILED] fixture {fixture_id}")
    return []


def analyze_match_events(home_team, away_team, events):
    home_score = away_score = 0
    home_2up = away_2up = False
    home_lead_minute = away_lead_minute = 0
    first_goal_side = None
    home_led = away_led = False
    home_early_goal = home_early_concede = False
    away_early_goal = away_early_concede = False
    home_first_half_for = home_first_half_against = 0
    home_second_half_for = home_second_half_against = 0
    away_first_half_for = away_first_half_against = 0
    away_second_half_for = away_second_half_against = 0

    for event in events:
        if event.get("type") != "Goal":
            continue
        scoring_team = event["team"]["name"]
        minute = event["time"]["elapsed"] or 0
        is_home_goal = scoring_team == home_team
        is_away_goal = scoring_team == away_team
        if is_home_goal:
            home_score += 1
        elif is_away_goal:
            away_score += 1
        else:
            continue
        if first_goal_side is None:
            first_goal_side = "home" if is_home_goal else "away"
        home_lead = home_score - away_score
        away_lead = away_score - home_score
        if home_lead >= 2:
            home_2up = True
            if home_lead_minute == 0:
                home_lead_minute = minute
        if away_lead >= 2:
            away_2up = True
            if away_lead_minute == 0:
                away_lead_minute = minute
        if home_lead > 0:
            home_led = True
        if away_lead > 0:
            away_led = True
        if minute <= EARLY_GOAL_CUTOFF:
            if is_home_goal:
                home_early_goal = True
                away_early_concede = True
            else:
                away_early_goal = True
                home_early_concede = True
        if minute <= HALF_CUTOFF:
            if is_home_goal:
                home_first_half_for += 1
                away_first_half_against += 1
            else:
                away_first_half_for += 1
                home_first_half_against += 1
        else:
            if is_home_goal:
                home_second_half_for += 1
                away_second_half_against += 1
            else:
                away_second_half_for += 1
                home_second_half_against += 1

    return {
        "final_home": home_score,
        "final_away": away_score,
        "home_2up": int(home_2up),
        "away_2up": int(away_2up),
        "home_turnaround": int(home_2up and home_score <= away_score),
        "away_turnaround": int(away_2up and away_score <= home_score),
        "home_lead_minute": home_lead_minute,
        "away_lead_minute": away_lead_minute,
        "home_early_goal": int(home_early_goal),
        "home_early_concede": int(home_early_concede),
        "away_early_goal": int(away_early_goal),
        "away_early_concede": int(away_early_concede),
        "home_first_lead": int(first_goal_side == "home"),
        "home_first_concede": int(first_goal_side == "away"),
        "away_first_lead": int(first_goal_side == "away"),
        "away_first_concede": int(first_goal_side == "home"),
        "home_led": int(home_led),
        "away_led": int(away_led),
        "home_first_half_for": home_first_half_for,
        "home_first_half_against": home_first_half_against,
        "home_second_half_for": home_second_half_for,
        "home_second_half_against": home_second_half_against,
        "away_first_half_for": away_first_half_for,
        "away_first_half_against": away_first_half_against,
        "away_second_half_for": away_second_half_for,
        "away_second_half_against": away_second_half_against,
    }


def save_result(fixture_id, league, home_team, away_team, analysis):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO match_results (
            match_id, league, home_team, away_team,
            final_home, final_away,
            home_2up, away_2up,
            home_turnaround, away_turnaround,
            home_lead_minute, away_lead_minute,
            home_early_goal, home_early_concede,
            away_early_goal, away_early_concede,
            home_first_lead, home_first_concede,
            away_first_lead, away_first_concede,
            home_led, away_led,
            home_first_half_for, home_first_half_against,
            home_second_half_for, home_second_half_against,
            away_first_half_for, away_first_half_against,
            away_second_half_for, away_second_half_against,
            processed_at
        ) VALUES (
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?
        )
        """,
        (
            str(fixture_id), league, home_team, away_team,
            analysis["final_home"], analysis["final_away"],
            analysis["home_2up"], analysis["away_2up"],
            analysis["home_turnaround"], analysis["away_turnaround"],
            analysis["home_lead_minute"], analysis["away_lead_minute"],
            analysis["home_early_goal"], analysis["home_early_concede"],
            analysis["away_early_goal"], analysis["away_early_concede"],
            analysis["home_first_lead"], analysis["home_first_concede"],
            analysis["away_first_lead"], analysis["away_first_concede"],
            analysis["home_led"], analysis["away_led"],
            analysis["home_first_half_for"], analysis["home_first_half_against"],
            analysis["home_second_half_for"], analysis["home_second_half_against"],
            analysis["away_first_half_for"], analysis["away_first_half_against"],
            analysis["away_second_half_for"], analysis["away_second_half_against"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def process_results():
    migrate_match_results()
    create_processed_fixtures_table()
    fixtures = get_completed_fixtures()
    processed = skipped = unsupported = failed = 0
    unmatched_leagues = set()

    for fixture in fixtures:
        fixture_id = fixture["fixture"]["id"]
        try:
            if fixture_already_processed(fixture_id):
                skipped += 1
                continue
            league_meta = fixture.get("league", {})
            league_id = league_meta.get("id")
            league_name = league_meta.get("name", "")
            country = league_meta.get("country", "")
            if league_id not in SUPPORTED_LEAGUE_IDS:
                unsupported += 1
                unmatched_leagues.add(f"{country} | {league_name} | id={league_id}")
                continue
            league = SUPPORTED_LEAGUE_IDS[league_id]
            home_team = fixture["teams"]["home"]["name"]
            away_team = fixture["teams"]["away"]["name"]
            events = get_fixture_events(fixture_id)
            if not events:
                failed += 1
                continue
            analysis = analyze_match_events(home_team, away_team, events)
            save_result(
                fixture_id,
                league,
                normalize_team(home_team),
                normalize_team(away_team),
                analysis,
            )
            mark_fixture_processed(fixture_id)
            processed += 1
            time.sleep(REQUEST_DELAY)
        except Exception as exc:
            failed += 1
            print(f"[FIXTURE ERROR] {fixture_id}: {exc}")
            continue

    print(f"{processed} fixtures processed")
    print(f"{skipped} fixtures skipped (already processed)")
    print(f"{unsupported} unsupported leagues ignored")
    print(f"{failed} fixtures failed (will retry next run)")
    if unmatched_leagues:
        print("\nLeague id/name/country seen but NOT in SUPPORTED_LEAGUE_IDS:")
        for name in sorted(unmatched_leagues):
            print(f"  - {name}")
    update_form_from_results()


if __name__ == "__main__":
    process_results()
