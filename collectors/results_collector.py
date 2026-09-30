import argparse
import os
from datetime import datetime, timedelta, timezone
import sqlite3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from constants import API_FOOTBALL_KEY, SUPPORTED_LEAGUE_IDS
from team_normalizer import normalize_team
from database import DB_NAME
from collectors import apisports as af
from collectors.backfill_apisports import BATCH, fixtures_with_events

# The live collector may use the quota down to this (the historical backfill
# stops much earlier, at APISPORTS_RESERVE).
af.RESERVE = int(os.environ.get("LIVE_RESERVE", "100"))
EXIT_PARTIAL = 3
# Cover ~full season so far from a mid-season date (Aug → now).
# Override: RESULTS_LOOKBACK_DAYS=90 python3 collectors/results_collector.py
LOOKBACK_DAYS = int(os.environ.get("RESULTS_LOOKBACK_DAYS", "75"))
EARLY_GOAL_CUTOFF = 30
HALF_CUTOFF = 45


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
    "match_date": "TEXT",
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


def unmark_fixture_processed(fixture_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM processed_fixtures WHERE fixture_id = ?",
        (str(fixture_id),),
    )
    conn.execute(
        "DELETE FROM match_results WHERE match_id = ?",
        (str(fixture_id),),
    )
    conn.commit()
    conn.close()


def clear_results_for_force(lookback_days):
    """Delete match_results + processed markers so the window can be rebuilt."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    conn = get_db()
    # processed_at / fixture markers from this window
    deleted_mr = conn.execute(
        "DELETE FROM match_results WHERE processed_at >= ? OR processed_at IS NULL",
        (cutoff,),
    ).rowcount
    # Safer full wipe of processed_fixtures for force season rebuild:
    # otherwise already-seen IDs outside the processed_at filter stay blocked.
    deleted_pf = conn.execute("DELETE FROM processed_fixtures").rowcount
    conn.commit()
    conn.close()
    print(f"[FORCE] cleared {deleted_mr} match_results rows (processed_at >= {cutoff[:10]}…)")
    print(f"[FORCE] cleared {deleted_pf} processed_fixtures markers")


def update_form_from_results():
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
            SELECT COALESCE(match_date, processed_at) AS processed_at,
                   final_home, final_away FROM match_results
            WHERE home_team = ?
            UNION ALL
            SELECT COALESCE(match_date, processed_at), final_away, final_home
            FROM match_results
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


def get_completed_fixtures(lookback_days):
    """Finished fixtures (all competitions) for the last N days: 1 call per day."""
    fixtures = []
    for day in range(lookback_days):
        target_date = (
            datetime.now(timezone.utc) - timedelta(days=day)
        ).strftime("%Y-%m-%d")
        payload = af.api_get("/fixtures", {"date": target_date, "status": "FT"})
        day_fixtures = payload.get("response") or []
        print(f"{target_date}: {len(day_fixtures)} fixtures")
        fixtures.extend(day_fixtures)
    print(f"Fixtures found: {len(fixtures)}")
    return fixtures


def get_season_fixtures():
    """
    Finished fixtures of the current season for every supported league:
    1 call per league (+ season lists, cached 7 days). Used to fill the season
    so far; the daily run then only needs a few days of lookback.
    """
    from collectors.backfill_apisports import league_seasons

    fixtures = []
    for league_id, league in SUPPORTED_LEAGUE_IDS.items():
        current = next((s for s in league_seasons(league_id) if s["current"]), None)
        if not current:
            print(f"{league}: no current season on api-sports")
            continue
        payload = af.api_get(
            "/fixtures",
            {"league": league_id, "season": current["year"], "status": "FT"},
        )
        rows = payload.get("response") or []
        for row in rows:  # listed by league, so the league is known
            row.setdefault("league", {}).setdefault("id", league_id)
        print(f"{league} {current['year']}: {len(rows)} finished")
        fixtures.extend(rows)
    print(f"Fixtures found: {len(fixtures)}")
    return fixtures


def _is_scoring_goal_event(event):
    """True only for events that change the scoreline.

    API-Football tags missed penalties as:
      type="Goal", detail="Missed Penalty"
    Those must never move the score or 2UP flags.
    """
    event_type = (event.get("type") or "").strip()
    detail = (event.get("detail") or "").strip().lower()
    comments = (event.get("comments") or "").strip().lower()

    if event_type.lower() in {"missed penalty", "missed_penalty"}:
        return False
    if event_type != "Goal":
        return False
    if "missed" in detail or "missed" in comments:
        return False
    if detail in {"missed penalty", "penalty missed"}:
        return False
    return True


def analyze_match_events(home_team, away_team, events, official_home=None, official_away=None):
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
    timeline = []  # [(minute, 1=home|2=away)] — used by the path model's behaviour features

    for event in events:
        if not _is_scoring_goal_event(event):
            continue

        detail = (event.get("detail") or "").strip().lower()
        team_name = (event.get("team") or {}).get("name") or ""
        minute = (event.get("time") or {}).get("elapsed") or 0

        if "own" in detail:
            if team_name == home_team:
                is_home_goal = False
                is_away_goal = True
            elif team_name == away_team:
                is_home_goal = True
                is_away_goal = False
            else:
                continue
        else:
            is_home_goal = team_name == home_team
            is_away_goal = team_name == away_team

        if is_home_goal:
            home_score += 1
        elif is_away_goal:
            away_score += 1
        else:
            continue
        timeline.append((int(minute or 0), 1 if is_home_goal else 2))

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

    if official_home is not None and official_away is not None:
        final_home = int(official_home)
        final_away = int(official_away)
    else:
        final_home = home_score
        final_away = away_score

    return {
        "goal_timeline": timeline,
        "final_home": final_home,
        "final_away": final_away,
        "home_2up": int(home_2up),
        "away_2up": int(away_2up),
        "home_turnaround": int(home_2up and final_home <= final_away),
        "away_turnaround": int(away_2up and final_away <= final_home),
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


LIVE_GOALS_DDL = """
CREATE TABLE IF NOT EXISTS live_goals (
    match_id TEXT NOT NULL, minute INTEGER, side INTEGER
)"""


def save_result(fixture_id, league, home_team, away_team, analysis, match_date=None):
    conn = get_db()
    conn.execute(LIVE_GOALS_DDL)
    conn.execute("DELETE FROM live_goals WHERE match_id = ?", (str(fixture_id),))
    conn.executemany(
        "INSERT INTO live_goals (match_id, minute, side) VALUES (?,?,?)",
        [(str(fixture_id), m, side) for m, side in analysis.get("goal_timeline") or []],
    )
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
            processed_at, match_date
        ) VALUES (
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?
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
            match_date,
        ),
    )
    conn.commit()
    conn.close()


def process_results(lookback_days=None, force=False, season_to_date=False):
    """Returns 0 when complete, EXIT_PARTIAL when stopped by quota/network."""
    lookback_days = lookback_days if lookback_days is not None else LOOKBACK_DAYS
    migrate_match_results()
    create_processed_fixtures_table()

    try:
        fixtures = get_season_fixtures() if season_to_date else get_completed_fixtures(lookback_days)
    except (af.QuotaExhausted, af.NetworkError) as exc:
        print(f"Could not list fixtures: {exc}")
        return EXIT_PARTIAL

    if force:
        if not fixtures:
            print("[FORCE] no fixtures fetched — refusing to clear existing results")
            sys.exit(1)
        from ops.backup import BackupError, backup_db
        try:
            backup_db("pre-results-force")
        except BackupError as exc:
            print(f"[FORCE] backup failed ({exc}) — refusing to clear results")
            sys.exit(1)
        print(f"[FORCE] season rebuild — lookback {lookback_days} days")
        clear_results_for_force(lookback_days)
    processed = skipped = unsupported = failed = 0
    unmatched_leagues = set()

    todo = []
    queued = set()
    for fixture in fixtures:
        fixture_id = fixture["fixture"]["id"]
        if fixture_id in queued:
            continue
        queued.add(fixture_id)
        if not force and fixture_already_processed(fixture_id):
            skipped += 1
            continue
        league_meta = fixture.get("league", {})
        league_id = league_meta.get("id")
        if league_id not in SUPPORTED_LEAGUE_IDS:
            unsupported += 1
            unmatched_leagues.add(
                f"{league_meta.get('country', '')} | {league_meta.get('name', '')} | id={league_id}"
            )
            continue
        todo.append(fixture)
    print(f"{len(todo)} new fixtures in supported leagues "
          f"(~{(len(todo) + BATCH - 1) // BATCH} event calls)")

    stopped = None
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        try:
            events_by_id = fixtures_with_events([f["fixture"]["id"] for f in batch])
        except (af.QuotaExhausted, af.NetworkError) as exc:
            stopped = str(exc)
            break
        for fixture in batch:
            fixture_id = fixture["fixture"]["id"]
            try:
                if force:
                    unmark_fixture_processed(fixture_id)
                league = SUPPORTED_LEAGUE_IDS[fixture["league"]["id"]]
                home_team = fixture["teams"]["home"]["name"]
                away_team = fixture["teams"]["away"]["name"]
                goals = fixture.get("goals") or {}
                official_home = goals.get("home")
                official_away = goals.get("away")
                events = events_by_id.get(fixture_id) or []
                if not events and official_home is None:
                    failed += 1
                    continue
                analysis = analyze_match_events(
                    home_team,
                    away_team,
                    events,
                    official_home=official_home,
                    official_away=official_away,
                )
                save_result(
                    fixture_id,
                    league,
                    normalize_team(home_team),
                    normalize_team(away_team),
                    analysis,
                    match_date=(fixture["fixture"].get("date") or "") or None,
                )
                mark_fixture_processed(fixture_id)
                processed += 1
            except Exception as exc:
                failed += 1
                print(f"[FIXTURE ERROR] {fixture_id}: {exc}")
        if processed and processed % 100 < BATCH:
            print(f"… {processed} processed so far")

    print(f"{processed} fixtures processed")
    print(f"{skipped} fixtures skipped (already processed)")
    print(f"{unsupported} unsupported leagues ignored")
    print(f"{failed} fixtures failed (will retry next run)")
    if stopped:
        print(f"Stopped early: {stopped} — rerun to continue")
    if unmatched_leagues:
        print("\nLeague id/name/country seen but NOT in SUPPORTED_LEAGUE_IDS:")
        for name in sorted(unmatched_leagues):
            print(f"  - {name}")
    update_form_from_results()
    return EXIT_PARTIAL if stopped else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect FT results + 2UP flags")
    parser.add_argument(
        "--days",
        type=int,
        default=LOOKBACK_DAYS,
        help=f"How many days back (default {LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear existing results in window and reprocess (fixes missed-pen rows)",
    )
    parser.add_argument(
        "--season-to-date",
        action="store_true",
        help="Fill the current season so far for every supported league (~1 call per league)",
    )
    args = parser.parse_args()
    if not API_FOOTBALL_KEY:
        print("[results] API_FOOTBALL_KEY is not set (see deploy/env.example)")
        sys.exit(2)
    if args.force and args.season_to_date:
        print("--force cannot be combined with --season-to-date")
        sys.exit(2)
    sys.exit(process_results(
        lookback_days=args.days, force=args.force, season_to_date=args.season_to_date,
    ))
