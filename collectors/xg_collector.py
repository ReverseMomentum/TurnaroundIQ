import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from collectors.thestatsapi import (
    finished_window,
    get_match_stats,
    kickoff_of,
    list_matches,
    match_id_of,
    supported_competition_ids,
    team_name,
)
from database import get_db
from progress import ProgressBar, ok, step, warn
from team_normalizer import normalize_team

FIXTURES_PER_LEAGUE = 10


def save_team_stats(team, avg_xg, avg_xga, goals_last5, conceded_last5, matches_played):
    xg_edge = None
    if avg_xg is not None and avg_xga is not None:
        xg_edge = round(avg_xg - avg_xga, 2)

    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO team_stats (team) VALUES (?)", (team,))
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


def _side_xg(block):
    if not isinstance(block, dict):
        return None
    value = block.get("xg")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _side_goals(block, fallback=None):
    if isinstance(block, dict):
        value = block.get("goals")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    if fallback is None:
        return 0.0
    try:
        return float(fallback)
    except (TypeError, ValueError):
        return 0.0


def process_xg():
    step("Resolving TheStatsAPI competitions")
    competitions = supported_competition_ids()
    date_from, date_to = finished_window(21)
    ok(f"Finished window {date_from} to {date_to}")
    team_data = {}

    bar = ProgressBar(len(competitions), label="Leagues")
    for league_name, competition_id in competitions.items():
        try:
            rows = list_matches(
                competition_id,
                status="finished",
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as exc:
            warn(f"{league_name}: match list failed ({exc})")
            bar.update(detail=league_name)
            continue

        rows.sort(key=lambda row: kickoff_of(row) or "")
        latest = rows[-FIXTURES_PER_LEAGUE:]
        ok(f"{league_name}: {len(rows)} finished, using last {len(latest)}")

        inner = ProgressBar(max(len(latest), 1), label="xG")
        for match in latest:
            mid = match_id_of(match)
            if not mid:
                inner.update(detail="no id")
                continue
            try:
                stats = get_match_stats(mid)
            except Exception as exc:
                warn(f"stats failed {mid}: {exc}")
                inner.update(detail=str(mid))
                continue

            home_block = stats.get("home") or {}
            away_block = stats.get("away") or {}
            home_team = normalize_team(
                team_name(home_block) or team_name(match.get("home_team") or match.get("home"))
            )
            away_team = normalize_team(
                team_name(away_block) or team_name(match.get("away_team") or match.get("away"))
            )
            if not home_team or not away_team:
                inner.update(detail="unnamed")
                continue

            score = match.get("score") or {}
            home_goals = _side_goals(home_block, score.get("home"))
            away_goals = _side_goals(away_block, score.get("away"))
            home_xg = _side_xg(home_block)
            away_xg = _side_xg(away_block)
            if home_xg is None:
                home_xg = home_goals
            if away_xg is None:
                away_xg = away_goals

            for team in (home_team, away_team):
                team_data.setdefault(
                    team,
                    {"xg": [], "xga": [], "goals": [], "conceded": []},
                )

            team_data[home_team]["xg"].append(home_xg)
            team_data[home_team]["xga"].append(away_xg)
            team_data[home_team]["goals"].append(home_goals)
            team_data[home_team]["conceded"].append(away_goals)
            team_data[away_team]["xg"].append(away_xg)
            team_data[away_team]["xga"].append(home_xg)
            team_data[away_team]["goals"].append(away_goals)
            team_data[away_team]["conceded"].append(home_goals)
            inner.update(detail=f"{home_team} v {away_team}")
        inner.finish()
        bar.update(detail=league_name)

    bar.finish()
    step("Writing team_stats")
    updated = 0
    write_bar = ProgressBar(max(len(team_data), 1), label="Teams")
    for team, values in team_data.items():
        n = len(values["xg"])
        if n == 0:
            write_bar.update(detail=team)
            continue
        save_team_stats(
            team,
            round(sum(values["xg"]) / n, 2),
            round(sum(values["xga"]) / n, 2),
            round(sum(values["goals"][-5:]), 2),
            round(sum(values["conceded"][-5:]), 2),
            n,
        )
        updated += 1
        write_bar.update(detail=team)
    write_bar.finish()
    ok(f"Updated {updated} teams")


if __name__ == "__main__":
    process_xg()
