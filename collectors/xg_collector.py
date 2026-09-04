import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from constants import SUPPORTED_LEAGUE_IDS
from team_normalizer import normalize_team

API_FOOTBALL_KEY = "aa7c72b2db786ed876c98fdafd5274b4"
DB_NAME = "two_up.db"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

# Last N finished games per league used for averages.
FIXTURES_PER_LEAGUE = 10
REQUEST_DELAY = 1.2


def season_candidates():
    year = datetime.now(timezone.utc).year
    return [year, year - 1, year - 2]


def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def save_team_stats(team, avg_xg, avg_xga, goals_last5, conceded_last5, matches_played):
    xg_edge = avg_xg - avg_xga
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO team_stats (team) VALUES (?)",
        (team,),
    )
    conn.execute(
        """
        UPDATE team_stats
        SET
            avg_xg = ?,
            avg_xga = ?,
            xg_edge = ?,
            goals_last5 = ?,
            conceded_last5 = ?,
            matches_played = ?,
            updated_at = ?
        WHERE team = ?
        """,
        (
            avg_xg,
            avg_xga,
            xg_edge,
            goals_last5,
            conceded_last5,
            matches_played,
            datetime.now(timezone.utc).isoformat(),
            team,
        ),
    )
    conn.commit()
    conn.close()


def fetch_finished_fixtures(league_id, season):
    url = (
        "https://v3.football.api-sports.io/fixtures"
        f"?league={league_id}&season={season}&status=FT"
    )
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    payload = response.json()

    errors = payload.get("errors")
    if errors:
        print(f"  API error league {league_id} season {season}: {errors}")

    rows = payload.get("response") or []
    rows.sort(key=lambda row: row.get("fixture", {}).get("date") or "")
    return rows


def get_recent_fixtures():
    fixtures = []
    seasons = season_candidates()
    print(f"Trying seasons {seasons}")

    for league_id, league_name in SUPPORTED_LEAGUE_IDS.items():
        found = False

        for season in seasons:
            try:
                rows = fetch_finished_fixtures(league_id, season)
            except Exception as exc:
                print(f"  Request failed {league_name} ({league_id}) {season}: {exc}")
                continue

            if not rows:
                continue

            latest = rows[-FIXTURES_PER_LEAGUE:]
            fixtures.extend(latest)
            print(
                f"{league_name} ({league_id}) season {season}: "
                f"{len(rows)} FT, using last {len(latest)}"
            )
            found = True
            break

        if not found:
            print(f"No fixtures found for {league_name} ({league_id})")

        time.sleep(REQUEST_DELAY)

    print(f"Fixtures queued for stats: {len(fixtures)}")
    return fixtures


def get_fixture_statistics(fixture_id):
    try:
        response = requests.get(
            "https://v3.football.api-sports.io/"
            f"fixtures/statistics?fixture={fixture_id}",
            headers=HEADERS,
            timeout=60,
        )
        if response.status_code == 429:
            print(f"Rate limited on fixture {fixture_id}, sleeping 20s")
            time.sleep(20)
            return []
        response.raise_for_status()
        return response.json().get("response") or []
    except Exception as exc:
        print(f"Stats failed fixture {fixture_id}: {exc}")
        return []


def extract_stat(stats, stat_name):
    for item in stats:
        if item.get("type") == stat_name:
            return item.get("value")
    return None


def process_xg():
    fixtures = get_recent_fixtures()
    team_data = {}

    for fixture in fixtures:
        fixture_id = fixture["fixture"]["id"]
        stats = get_fixture_statistics(fixture_id)
        time.sleep(REQUEST_DELAY)

        if len(stats) < 2:
            continue

        home_team = normalize_team(stats[0]["team"]["name"])
        away_team = normalize_team(stats[1]["team"]["name"])
        home_stats = stats[0]["statistics"]
        away_stats = stats[1]["statistics"]

        home_goals = fixture["goals"]["home"] or 0
        away_goals = fixture["goals"]["away"] or 0

        home_xg = extract_stat(home_stats, "Expected Goals")
        away_xg = extract_stat(away_stats, "Expected Goals")

        try:
            home_xg = float(home_xg)
        except (TypeError, ValueError):
            home_xg = float(home_goals)

        try:
            away_xg = float(away_xg)
        except (TypeError, ValueError):
            away_xg = float(away_goals)

        for team in (home_team, away_team):
            if team not in team_data:
                team_data[team] = {
                    "xg": [],
                    "xga": [],
                    "goals": [],
                    "conceded": [],
                }

        team_data[home_team]["xg"].append(home_xg)
        team_data[home_team]["xga"].append(away_xg)
        team_data[home_team]["goals"].append(home_goals)
        team_data[home_team]["conceded"].append(away_goals)

        team_data[away_team]["xg"].append(away_xg)
        team_data[away_team]["xga"].append(home_xg)
        team_data[away_team]["goals"].append(away_goals)
        team_data[away_team]["conceded"].append(home_goals)

    updated = 0
    for team, values in team_data.items():
        matches_played = len(values["xg"])
        if matches_played == 0:
            continue

        save_team_stats(
            team,
            round(sum(values["xg"]) / matches_played, 2),
            round(sum(values["xga"]) / matches_played, 2),
            round(sum(values["goals"][-5:]), 2),
            round(sum(values["conceded"][-5:]), 2),
            matches_played,
        )
        updated += 1

    print(f"Updated {updated} teams")


if __name__ == "__main__":
    process_xg()
