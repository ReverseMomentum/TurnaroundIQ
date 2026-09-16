"""
Recent-form weighting for Early Goal Hunter + Chaos Index.

Long-run team_stats still used as a prior; last N finished games
carry most of the weight when enough sample exists.
"""

from database import get_db

DEFAULT_N = 10
MIN_N = 5
# When sample >= MIN_N: this weight on recent, rest on long-run prior
RECENT_WEIGHT = 0.70


def _blend(recent, prior, n, min_n=MIN_N, recent_w=RECENT_WEIGHT):
    if recent is None:
        return prior
    if prior is None:
        return recent
    if n < min_n:
        # not enough recent games — ease in
        w = recent_w * (n / float(min_n))
    else:
        w = recent_w
    return w * recent + (1.0 - w) * prior


def recent_score_form(team, n=DEFAULT_N):
    """
    Last n games for team from match_results then historical_matches.
    Returns rates 0–100: btts, o2_5, early_goal, early_concede,
    scores_first, concedes_first, and sample size.
    """
    conn = get_db()
    games = []

    # Live results first (have early / first-lead flags)
    try:
        rows = conn.execute(
            """
            SELECT processed_at,
                   home_team, away_team, final_home, final_away,
                   home_early_goal, away_early_goal,
                   home_early_concede, away_early_concede,
                   home_first_lead, away_first_lead
            FROM match_results
            WHERE home_team = ? OR away_team = ?
            ORDER BY processed_at DESC, id DESC
            LIMIT ?
            """,
            (team, team, n),
        ).fetchall()
        for row in rows:
            is_home = row[1] == team
            fh, fa = row[3], row[4]
            if is_home:
                early_g = row[5]
                early_c = row[7]
                first = row[9]
            else:
                early_g = row[6]
                early_c = row[8]
                first = row[10]
            games.append({
                "fh": fh,
                "fa": fa,
                "early_goal": int(early_g or 0),
                "early_concede": int(early_c or 0),
                "scores_first": int(first or 0),
                "has_flags": True,
            })
    except Exception:
        pass

    # Pad with historical finals if needed (no early flags)
    if len(games) < n:
        need = n - len(games)
        try:
            rows = conn.execute(
                """
                SELECT date, home_team, away_team, final_home, final_away
                FROM historical_matches
                WHERE home_team = ? OR away_team = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (team, team, need + 20),
            ).fetchall()
            for row in rows:
                if len(games) >= n:
                    break
                games.append({
                    "fh": row[3],
                    "fa": row[4],
                    "early_goal": None,
                    "early_concede": None,
                    "scores_first": None,
                    "has_flags": False,
                })
        except Exception:
            pass

    conn.close()
    games = games[:n]
    if not games:
        return {
            "sample": 0,
            "btts": None,
            "o2_5": None,
            "early_goal": None,
            "early_concede": None,
            "scores_first": None,
            "concedes_first": None,
        }

    n_scored = btts = o25 = 0
    early_g = early_c = first = first_n = 0
    for g in games:
        fh, fa = g["fh"], g["fa"]
        if fh is None or fa is None:
            continue
        n_scored += 1
        if fh > 0 and fa > 0:
            btts += 1
        if (fh + fa) >= 3:
            o25 += 1
        if g["has_flags"]:
            first_n += 1
            early_g += g["early_goal"] or 0
            early_c += g["early_concede"] or 0
            first += g["scores_first"] or 0

    def rate(num, den):
        if den <= 0:
            return None
        return 100.0 * num / den

    return {
        "sample": len(games),
        "btts": rate(btts, n_scored),
        "o2_5": rate(o25, n_scored),
        "early_goal": rate(early_g, first_n),
        "early_concede": rate(early_c, first_n),
        "scores_first": rate(first, first_n),
        "concedes_first": rate(first_n - first, first_n) if first_n else None,
    }


def blended_rate(recent_val, prior_val, sample, min_n=MIN_N, recent_w=RECENT_WEIGHT):
    return _blend(recent_val, prior_val, sample, min_n=min_n, recent_w=recent_w)
