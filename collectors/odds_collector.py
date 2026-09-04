import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from collectors.thestatsapi import (
    get_match_odds,
    kickoff_of,
    list_matches,
    match_id_of,
    supported_competition_ids,
    team_name,
    upcoming_window,
)
from constants import THESTATSAPI_PREFERRED_BOOKS
from database import (
    fixture_recently_checked,
    get_db,
    save_odds_history,
    update_fixture_cache,
)
from team_normalizer import normalize_team

LOOKAHEAD_DAYS = 2
CACHE_MINUTES = 30

BOOK_ALIASES = {
    "bet365": "bet365",
    "pinnacle": "pinnacle",
    "paddy power": "paddypower",
    "paddypower": "paddypower",
    "betfair sportsbook": "betfair_sb",
    "betfair": "betfair_sb",
    "kambi": "kambi",
}


def _price(outcome):
    if outcome is None:
        return None
    if isinstance(outcome, (int, float)):
        return float(outcome)
    if isinstance(outcome, str):
        try:
            return float(outcome)
        except ValueError:
            return None
    if isinstance(outcome, dict):
        for key in ("last_seen", "price", "odds", "opening"):
            if outcome.get(key) is not None:
                try:
                    return float(outcome[key])
                except (TypeError, ValueError):
                    continue
    return None


def _match_odds_market(markets):
    if not isinstance(markets, dict):
        return {}
    for key in ("match_odds", "1x2", "full_time", "home_draw_away"):
        if key in markets:
            return markets[key] or {}
    return markets


def extract_back_prices(odds_payload):
    """
    Return {bookmaker_key: {home, away, draw}} from a TheStatsAPI odds payload.
    Lay is never required.
    """
    data = odds_payload or {}
    books = data.get("bookmakers") or data.get("odds") or []
    if isinstance(books, dict):
        books = [
            {"bookmaker": name, "markets": payload}
            for name, payload in books.items()
        ]

    collected = {}
    for entry in books:
        raw_name = (
            entry.get("bookmaker")
            or entry.get("name")
            or entry.get("bookmaker_name")
            or ""
        )
        key = BOOK_ALIASES.get(str(raw_name).strip().lower())
        if not key:
            continue
        market = _match_odds_market(entry.get("markets") or entry)
        home = _price(market.get("home"))
        away = _price(market.get("away"))
        draw = _price(market.get("draw"))
        if home is None and away is None:
            continue
        collected[key] = {"home": home, "away": away, "draw": draw, "label": raw_name}
    return collected


def pick_books(collected):
    if not collected:
        return {}
    preferred = []
    for label in THESTATSAPI_PREFERRED_BOOKS:
        key = BOOK_ALIASES.get(label.lower())
        if key and key in collected:
            preferred.append(key)
    if preferred:
        return {key: collected[key] for key in preferred}
    # Fall back to whatever 1X2 books came back.
    return collected


def ensure_team_row(team):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
    conn.commit()
    conn.close()


def collect_odds():
    competitions = supported_competition_ids()
    date_from, date_to = upcoming_window(LOOKAHEAD_DAYS)
    print(f"Upcoming window {date_from} to {date_to}")

    saved = 0
    skipped = 0

    for league_name, competition_id in competitions.items():
        try:
            fixtures = list_matches(
                competition_id,
                status="scheduled",
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as exc:
            print(f"{league_name}: fixture list failed ({exc})")
            continue

        print(f"{league_name}: {len(fixtures)} scheduled")

        for fixture in fixtures:
            fixture_id = match_id_of(fixture)
            if not fixture_id:
                skipped += 1
                continue

            if fixture_recently_checked(fixture_id, CACHE_MINUTES):
                skipped += 1
                continue

            home_team = normalize_team(
                team_name(fixture.get("home_team") or fixture.get("home"))
            )
            away_team = normalize_team(
                team_name(fixture.get("away_team") or fixture.get("away"))
            )
            kickoff = kickoff_of(fixture)
            if not home_team or not away_team:
                skipped += 1
                continue

            ensure_team_row(home_team)
            ensure_team_row(away_team)

            try:
                odds_payload = get_match_odds(fixture_id)
            except Exception as exc:
                print(f"  odds failed {fixture_id}: {exc}")
                skipped += 1
                continue

            books = pick_books(extract_back_prices(odds_payload))
            if not books:
                skipped += 1
                update_fixture_cache(fixture_id, kickoff)
                continue

            for bookmaker, prices in books.items():
                if prices.get("home") is not None:
                    save_odds_history(
                        match_id=fixture_id,
                        kickoff=kickoff,
                        league=league_name,
                        home_team=home_team,
                        away_team=away_team,
                        selection=home_team,
                        bookmaker=bookmaker,
                        back_odds=prices["home"],
                        lay_odds=None,
                    )
                    saved += 1
                if prices.get("away") is not None:
                    save_odds_history(
                        match_id=fixture_id,
                        kickoff=kickoff,
                        league=league_name,
                        home_team=home_team,
                        away_team=away_team,
                        selection=away_team,
                        bookmaker=bookmaker,
                        back_odds=prices["away"],
                        lay_odds=None,
                    )
                    saved += 1

            update_fixture_cache(fixture_id, kickoff)

    print(f"Saved {saved} back-odds rows (lay left empty)")
    print(f"Skipped {skipped} fixtures")


if __name__ == "__main__":
    collect_odds()
