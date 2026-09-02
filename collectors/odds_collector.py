import time
import requests

from datetime import (
    datetime,
    timedelta
)

import sys
from pathlib import Path

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(
        str(PROJECT_ROOT)
    )

from database import (
    save_odds_history,
    get_tracked_teams,
    fixture_recently_checked,
    update_fixture_cache
)

from team_normalizer import (
    normalize_team
)

from bookmakers import (
    get_enabled_bookmakers
)

# ==================================
# CONFIG
# ==================================

API_KEY = "cb23a6f3-5d30-47f1-8f0c-33137e430799"

BASE_URL = "https://api.oddspapi.io/v4"

SPORT_ID = 10

LOOKAHEAD_DAYS = 1

REQUEST_DELAY = 10

CACHE_MINUTES = 30

# ==================================
# FIXTURES
# ==================================


def get_fixtures():

    now = datetime.utcnow()

    future = (
        now +
        timedelta(
            days=LOOKAHEAD_DAYS
        )
    )

    response = requests.get(
        f"{BASE_URL}/fixtures",
        params={
            "sportId": SPORT_ID,
            "statusId": 0,
            "hasOdds": "true",
            "from": now.strftime(
                "%Y-%m-%d"
            ),
            "to": future.strftime(
                "%Y-%m-%d"
            ),
            "apiKey": API_KEY
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ==================================
# ODDS
# ==================================


def get_fixture_odds(
    fixture_id,
    bookmaker
):

    response = requests.get(
        f"{BASE_URL}/odds",
        params={
            "fixtureId": fixture_id,
            "bookmakers": bookmaker,
            "oddsFormat": "decimal",
            "language": "en",
            "verbosity": 3,
            "apiKey": API_KEY
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ==================================
# PARSER
# ==================================


def extract_match_odds(
    odds_data,
    bookmaker
):

    bookmaker_data = (
        odds_data
        .get(
            "bookmakerOdds",
            {}
        )
        .get(
            bookmaker,
            {}
        )
    )

    if not bookmaker_data:
        return {}

    markets = bookmaker_data.get(
        "markets",
        {}
    )

    prices = {}

    for market in markets.values():

        outcomes = market.get(
            "outcomes",
            {}
        )

        for outcome in outcomes.values():

            players = outcome.get(
                "players",
                {}
            )

            for player in players.values():

                outcome_id = str(
                    player.get(
                        "bookmakerOutcomeId",
                        ""
                    )
                ).lower()

                price = player.get(
                    "price"
                )

                if price is None:
                    continue

                if outcome_id == "home":

                    prices["home"] = float(
                        price
                    )

                elif outcome_id == "away":

                    prices["away"] = float(
                        price
                    )

                elif outcome_id == "draw":

                    prices["draw"] = float(
                        price
                    )

    return prices


# ==================================
# COLLECTOR
# ==================================


def collect_odds():

    bookmakers = (
        get_enabled_bookmakers()
    )

    fixtures = (
        get_fixtures()
    )

    tracked_teams = (
        get_tracked_teams()
    )

    print(
        f"Found {len(fixtures)} fixtures"
    )

    saved_rows = 0

    skipped_rows = 0

    for fixture in fixtures:

        fixture_id = (
            fixture["fixtureId"]
        )

        kickoff = (
            fixture["startTime"]
        )

        league = (
            fixture["tournamentName"]
        )

        home_team = (
            normalize_team(
                fixture[
                    "participant1Name"
                ]
            )
        )

        away_team = (
            normalize_team(
                fixture[
                    "participant2Name"
                ]
            )
        )

        # Skip teams not in
        # the ML database

        if (
            home_team not in tracked_teams
            or
            away_team not in tracked_teams
        ):

            skipped_rows += 1

            continue

        # Cache Protection

        if fixture_recently_checked(
            fixture_id,
            CACHE_MINUTES
        ):

            skipped_rows += 1

            continue

        for bookmaker in bookmakers:

            try:

                odds_data = (
                    get_fixture_odds(
                        fixture_id,
                        bookmaker
                    )
                )

                prices = (
                    extract_match_odds(
                        odds_data,
                        bookmaker
                    )
                )

                if "home" in prices:

                    save_odds_history(
                        match_id=
                        fixture_id,

                        kickoff=
                        kickoff,

                        league=
                        league,

                        home_team=
                        home_team,

                        away_team=
                        away_team,

                        selection=
                        home_team,

                        bookmaker=
                        bookmaker,

                        back_odds=
                        prices["home"]
                    )

                    saved_rows += 1

                if "away" in prices:

                    save_odds_history(
                        match_id=
                        fixture_id,

                        kickoff=
                        kickoff,

                        league=
                        league,

                        home_team=
                        home_team,

                        away_team=
                        away_team,

                        selection=
                        away_team,

                        bookmaker=
                        bookmaker,

                        back_odds=
                        prices["away"]
                    )

                    saved_rows += 1

                time.sleep(
                    REQUEST_DELAY
                )

            except Exception as exc:

                if "429" in str(exc):

                    print(
                        "Rate limit reached."
                    )

                    print(
                        "Sleeping 60 seconds..."
                    )

                    time.sleep(60)

                    continue

                print(
                    f"[ERROR] "
                    f"{fixture_id} "
                    f"{bookmaker}"
                )

                print(exc)

                continue

        update_fixture_cache(
            fixture_id,
            kickoff
        )

    print(
        f"Saved {saved_rows} odds rows"
    )

    print(
        f"Skipped {skipped_rows} fixtures"
    )


# ==================================
# RUN
# ==================================

if __name__ == "__main__":

    collect_odds()
