"""
Live monitor: in-play state of users' open 2UP bets, and live games where a team
is 2 up right now. Data from api-sports (same key and daily budget as the rest).

Calls are shared by everyone and cached:
  - /fixtures?ids=...  (up to 20 per call, with goal events) for fixtures that
    have an open tracked bet, at most once per LIVE_TTL seconds per fixture
  - /fixtures?live=all once per LIVE_TTL seconds for the "2 up right now" list
So the monitor costs ~2 calls a minute while someone has it open, and nothing
otherwise.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from collectors.backfill_apisports import is_scoring_goal, resolve_goals
from constants import API_FOOTBALL_KEY, SUPPORTED_LEAGUE_IDS
from team_normalizer import normalize_team

LIVE_TTL = 60          # seconds between refreshes of a live fixture
IDLE_TTL = 600         # not started yet
DONE_TTL = 6 * 3600    # finished: the result won't change
IN_PLAY = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}
FINISHED = {"FT", "AET", "PEN"}
DEAD = {"PST", "CANC", "ABD", "AWD", "WO"}

TIMEOUT = 12            # seconds: the page must never hang on api-sports

_fixtures = {}            # fixture_id -> (fetched_at, state)
_live_all = {"ts": 0.0, "states": []}
_lock = threading.Lock()


def _get(path, params):
    """One quick api-sports call (no retries: the next refresh is a minute away).
    The shared collectors.apisports client retries for minutes, fine for night jobs only."""
    if not API_FOOTBALL_KEY:
        raise RuntimeError("API_FOOTBALL_KEY missing")
    resp = requests.get("https://v3.football.api-sports.io" + path, params=params,
                        headers={"x-apisports-key": API_FOOTBALL_KEY}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _phase(short):
    if short in IN_PLAY:
        return "live"
    if short in FINISHED:
        return "finished"
    if short in DEAD:
        return "off"
    return "upcoming"


def parse_fixture(item):
    """api-sports fixture -> compact state. goals = [(minute, side)] when the
    goal events reproduce the score, else None (score-only)."""
    fx, league = item.get("fixture") or {}, item.get("league") or {}
    teams, goals = item.get("teams") or {}, item.get("goals") or {}
    status = fx.get("status") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    gh, ga = goals.get("home"), goals.get("away")
    gh, ga = int(gh or 0), int(ga or 0)
    home_name, away_name = normalize_team(home.get("name") or ""), normalize_team(away.get("name") or "")
    timeline = None
    events = item.get("events")
    if events is not None:
        if not [e for e in events if is_scoring_goal(e)] and gh + ga == 0:
            timeline = []
        else:
            rows, _rule, _why = resolve_goals(events, home.get("id"), away.get("id"),
                                              home_name, away_name, gh, ga)
            if rows is not None:
                timeline = [(int(r[0] or 0), r[1]) for r in rows]
    elapsed = status.get("elapsed")
    return {
        "fixture_id": str(fx.get("id") or ""),
        "league_id": league.get("id"),
        "league": SUPPORTED_LEAGUE_IDS.get(league.get("id"), league.get("name") or ""),
        "kickoff": fx.get("date"),
        "status": status.get("short") or "",
        "phase": _phase(status.get("short") or ""),
        "minute": int(elapsed) if elapsed is not None else None,
        "extra": status.get("extra"),
        "home_team": home_name, "away_team": away_name,
        "home_goals": gh, "away_goals": ga,
        "goals": timeline,
    }


def side_summary(state, side):
    """From one side's point of view: score, ever 2 up, when, currently winning."""
    tg = state["home_goals"] if side == 1 else state["away_goals"]
    og = state["away_goals"] if side == 1 else state["home_goals"]
    two_up_minute, known = None, state["goals"] is not None
    if known:
        a = b = 0
        for minute, s in state["goals"]:
            if s == side:
                a += 1
            else:
                b += 1
            if a - b >= 2:
                two_up_minute = minute
                break
    elif tg - og >= 2:
        two_up_minute = state["minute"]   # 2 up now; earlier history unknown
    return {"team_goals": tg, "opp_goals": og, "went_2up": two_up_minute is not None,
            "two_up_minute": two_up_minute, "history_known": known,
            "winning": tg > og}


def _ttl(state):
    return {"live": LIVE_TTL, "finished": DONE_TTL, "off": DONE_TTL}.get(state["phase"], IDLE_TTL)


def fixture_states(ids, now=None):
    """{fixture_id: state} for these api-sports fixture ids, refreshing stale ones."""
    now = now or time.time()
    ids = [str(i) for i in ids if str(i or "").isdigit()]
    with _lock:
        stale = [i for i in ids if i not in _fixtures or now - _fixtures[i][0] >= _ttl(_fixtures[i][1])]
        for k in range(0, len(stale), 20):
            batch = stale[k:k + 20]
            try:
                payload = _get("/fixtures", {"ids": "-".join(batch)})
            except Exception:
                break  # quota / network: serve what we have
            for item in payload.get("response") or []:
                st = parse_fixture(item)
                _fixtures[st["fixture_id"]] = (now, st)
        return {i: _fixtures[i][1] for i in ids if i in _fixtures}


def live_now(now=None):
    """Live games in our leagues (shared, cached LIVE_TTL)."""
    now = now or time.time()
    with _lock:
        if now - _live_all["ts"] >= LIVE_TTL:
            try:
                payload = _get("/fixtures", {"live": "all"})
                states = [parse_fixture(i) for i in payload.get("response") or []
                          if (i.get("league") or {}).get("id") in SUPPORTED_LEAGUE_IDS]
                _live_all.update(ts=now, states=states)
            except Exception:
                pass
        return list(_live_all["states"])


def _chance(team, opp, league, is_home, state, summary):
    """Live turnaround chance once the side has been 2 up and the game is on."""
    if state["phase"] != "live" or not summary["went_2up"] or state["minute"] is None:
        return None
    try:
        from models import live_turnaround
        out = live_turnaround.predict_live(team, opp, league, is_home, state["minute"],
                                           summary["team_goals"], summary["opp_goals"])
        return out["no_win_pct"] if out else None
    except Exception:
        return None


def bet_view(bet, state):
    """A tracked bet plus its live state (state may be None)."""
    base = {"tracked_id": bet["id"], "match": bet.get("match") or f"{bet['home_team']} vs {bet['away_team']}",
            "home_team": bet["home_team"], "away_team": bet["away_team"], "team": bet["team"],
            "league": bet.get("league") or "", "kickoff": bet.get("kickoff"),
            "stake": bet.get("stake"), "back_odds": bet.get("back_odds"), "lay_odds": bet.get("lay_odds"),
            "bet": bet}
    if not state:
        return {**base, "phase": "unknown" if not bet.get("match_id") else "upcoming"}
    is_home = bet["team"] == bet["home_team"]
    s = side_summary(state, 1 if is_home else 2)
    opp = bet["away_team"] if is_home else bet["home_team"]
    if state["phase"] == "finished":
        verdict = "turnaround" if s["went_2up"] and not s["winning"] else (
            "held" if s["went_2up"] else "no_2up")
    elif s["went_2up"]:
        verdict = "comeback_on" if not s["winning"] else "triggered"
    else:
        verdict = "waiting"
    return {**base, **s, "phase": state["phase"], "status": state["status"], "minute": state["minute"],
            "extra": state["extra"], "verdict": verdict,
            "turnaround_pct": _chance(bet["team"], opp, base["league"], is_home, state, s)}


def live_view(state):
    """A live game where a team is 2+ up now (or was, if the timeline is known)."""
    out = []
    for side in (1, 2):
        s = side_summary(state, side)
        if not s["went_2up"]:
            continue
        team = state["home_team"] if side == 1 else state["away_team"]
        opp = state["away_team"] if side == 1 else state["home_team"]
        out.append({"fixture_id": state["fixture_id"], "league": state["league"],
                    "home_team": state["home_team"], "away_team": state["away_team"],
                    "home_goals": state["home_goals"], "away_goals": state["away_goals"],
                    "minute": state["minute"], "status": state["status"], "team": team, **s,
                    "comeback_on": not s["winning"],
                    "turnaround_pct": _chance(team, opp, state["league"], side == 1, state, s)})
    return out


def monitor(open_bets, now=None):
    """Everything the Live page shows. open_bets: the user's open FTA tracked bets."""
    now_dt = datetime.now(timezone.utc)
    window = []
    for b in open_bets:
        try:
            ko = datetime.fromisoformat(str(b.get("kickoff")).replace("Z", "+00:00"))
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
        except ValueError:
            ko = None
        # from 3h before kick-off until 4h after (extra time, slow settlement)
        if ko is None or now_dt - timedelta(hours=4) <= ko <= now_dt + timedelta(hours=3):
            window.append(b)
    states = fixture_states([b.get("match_id") for b in window], now)
    bets = [bet_view(b, states.get(str(b.get("match_id") or ""))) for b in window]
    order = {"live": 0, "upcoming": 1, "finished": 2, "off": 3, "unknown": 4}
    bets.sort(key=lambda v: (order.get(v["phase"], 5), str(v.get("kickoff") or "")))
    games = [g for st in live_now(now) for g in live_view(st)]
    games.sort(key=lambda g: -(g["turnaround_pct"] if g["turnaround_pct"] is not None else -1))
    return {"my_bets": bets, "live_now": games, "refresh_s": LIVE_TTL,
            "updated_at": now_dt.isoformat()}
