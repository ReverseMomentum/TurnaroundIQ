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

from database import get_db, get_odds_movement

from calculations import (
    calculate_lay_stake,
    calculate_liability,
    calculate_qualifying_loss,
    calculate_fta_profit,
    calculate_expected_profit,
    calculate_ev_percent,
    calculate_ev_rating,
    calculate_ranking_score
)

from models.model import (
    predict_with_confidence,
    build_feature_vector
)


TEAM_STATS_COLUMNS = [

    "avg_xg",
    "avg_xga",

    "xg_edge",

    "goals_last5",
    "conceded_last5",

    "turnaround_pct",
    "two_up_trigger_rate",

    "historical_turnaround_rate",
    "historical_trigger_rate",

    "early_goal_rate",
    "early_concede_rate",

    "first_lead_rate",
    "first_concede_rate",

    "comeback_rate",
    "lead_retention_rate",

    "first_half_goal_diff",
    "second_half_goal_diff",

    "burnout_index",

    "league_turnaround_rate",
    "opponent_turnaround_rate",

    "live_trigger_rate",
    "live_early_goal_rate",
    "live_early_concede_rate",
    "live_first_lead_rate",
    "live_first_concede_rate",
    "live_comeback_rate",
    "live_lead_retention_rate",
    "live_first_half_goal_diff",
    "live_second_half_goal_diff",
    "live_burnout_index",

    "trigger_rate_delta",
    "early_goal_delta",
    "early_concede_delta",
    "first_lead_delta",
    "first_concede_delta",
    "comeback_delta",
    "lead_retention_delta",
    "burnout_delta",

    "abs_trigger_delta",
    "abs_retention_delta"
]


def estimate_lay_odds(
    back_odds
):

    if back_odds < 2:
        margin = 0.03

    elif back_odds < 5:
        margin = 0.05

    else:
        margin = 0.08

    return round(
        back_odds * (1 + margin),
        2
    )


def get_team_stats(
    team
):

    conn = get_db()

    columns_sql = ",\n            ".join(
        TEAM_STATS_COLUMNS
    )

    row = conn.execute(
        f"""
        SELECT

            {columns_sql}

        FROM team_stats

        WHERE team = ?
        """,
        (team,)
    ).fetchone()

    conn.close()

    if not row:
        return None

    return dict(
        zip(
            TEAM_STATS_COLUMNS,
            row
        )
    )


def build_opportunity(
    fixture,
    stake=40,
    commission=2
):

    team = fixture["team"]

    stats = get_team_stats(
        team
    )

    if not stats:
        return None

    back_odds = float(
        fixture["back_odds"]
    )

    supplied_lay = fixture.get(
        "lay_odds"
    )

    estimated_lay = False

    if supplied_lay is None:

        lay_odds = estimate_lay_odds(
            back_odds
        )

        estimated_lay = True

    else:

        lay_odds = float(
            supplied_lay
        )

    # opening_back_odds / odds_movement come from odds_history
    # (pre-match polls already captured by odds_collector.py),
    # not from the current back_odds being used to stake this
    # bet - those are two different things. If the fixture
    # doesn't carry both team names we can't look this up, and
    # it's left as None -> NaN for the model, same as any other
    # genuinely missing feature.
    home_team = fixture.get(
        "home_team"
    )

    away_team = fixture.get(
        "away_team"
    )

    opening_back_odds = None
    odds_movement = None

    if home_team and away_team:

        opening_back_odds, odds_movement = (
            get_odds_movement(
                home_team,
                away_team,
                team
            )
        )

    feature_vector = (
        build_feature_vector(
            team_stats=stats,

            is_home=fixture.get(
                "is_home",
                True
            ),

            opening_back_odds=
            opening_back_odds,

            odds_movement=
            odds_movement,

            lead_minute=0,
            max_lead=2,

            shots_for=0,
            shots_against=0,

            red_cards_for=0,
            red_cards_against=0
        )
    )

    prediction = (
        predict_with_confidence(
            feature_vector
        )
    )

    fta_pct = prediction[
        "fta_pct"
    ]

    confidence = prediction[
        "confidence"
    ]

    lay_stake = (
        calculate_lay_stake(
            back_odds,
            lay_odds,
            stake,
            commission
        )
    )

    liability = (
        calculate_liability(
            lay_odds,
            lay_stake
        )
    )

    qualifying_loss = (
        calculate_qualifying_loss(
            back_odds,
            lay_odds,
            stake,
            lay_stake,
            commission
        )
    )

    ql_percent = (
        abs(
            qualifying_loss
        )
        /
        stake
    ) * 100

    fta_profit = (
        calculate_fta_profit(
            stake,
            back_odds,
            lay_stake,
            commission
        )
    )

    expected_profit = (
        calculate_expected_profit(
            fta_profit,
            qualifying_loss,
            fta_pct
        )
    )

    ev_percent = (
        calculate_ev_percent(
            expected_profit,
            qualifying_loss
        )
    )

    ev_rating = (
        calculate_ev_rating(
            fta_pct,
            qualifying_loss,
            stake
        )
    )

    ranking_score = (
        calculate_ranking_score(
            expected_profit,
            fta_pct
        )
    )

    return {

        "match":
            fixture.get(
                "match",
                ""
            ),

        "team":
            team,

        "league":
            fixture.get(
                "league",
                ""
            ),

        "bookmaker":
            fixture.get(
                "bookmaker",
                ""
            ),

        "back_odds":
            round(
                back_odds,
                2
            ),

        "lay_odds":
            round(
                lay_odds,
                2
            ),

        "estimated_lay":
            estimated_lay,

        "stake":
            stake,

        "commission":
            commission,

        "fta_pct":
            round(
                fta_pct,
                2
            ),

        "confidence":
            round(
                confidence,
                2
            ),

        "lay_stake":
            round(
                lay_stake,
                2
            ),

        "liability":
            round(
                liability,
                2
            ),

        "qualifying_loss":
            round(
                qualifying_loss,
                2
            ),

        "ql_percent":
            round(
                ql_percent,
                2
            ),

        "fta_profit":
            round(
                fta_profit,
                2
            ),

        "expected_profit":
            round(
                expected_profit,
                2
            ),

        "ev_percent":
            round(
                ev_percent,
                2
            ),

        "ev_rating":
            round(
                ev_rating,
                2
            ),

        "ranking_score":
            round(
                ranking_score,
                4
            )
    }


def rebuild_opportunity(
    opportunity,
    lay_odds,
    commission
):

    back_odds = (
        opportunity["back_odds"]
    )

    stake = (
        opportunity["stake"]
    )

    lay_stake = (
        calculate_lay_stake(
            back_odds,
            lay_odds,
            stake,
            commission
        )
    )

    liability = (
        calculate_liability(
            lay_odds,
            lay_stake
        )
    )

    qualifying_loss = (
        calculate_qualifying_loss(
            back_odds,
            lay_odds,
            stake,
            lay_stake,
            commission
        )
    )

    ql_percent = (
        abs(
            qualifying_loss
        )
        /
        stake
    ) * 100

    fta_profit = (
        calculate_fta_profit(
            stake,
            back_odds,
            lay_stake,
            commission
        )
    )

    expected_profit = (
        calculate_expected_profit(
            fta_profit,
            qualifying_loss,
            opportunity[
                "fta_pct"
            ]
        )
    )

    ev_percent = (
        calculate_ev_percent(
            expected_profit,
            qualifying_loss
        )
    )

    ev_rating = (
        calculate_ev_rating(
            opportunity[
                "fta_pct"
            ],
            qualifying_loss,
            stake
        )
    )

    updated = dict(
        opportunity
    )

    updated["lay_odds"] = round(
        lay_odds,
        2
    )

    updated["commission"] = (
        commission
    )

    updated["estimated_lay"] = (
        False
    )

    updated["lay_stake"] = round(
        lay_stake,
        2
    )

    updated["liability"] = round(
        liability,
        2
    )

    updated["qualifying_loss"] = round(
        qualifying_loss,
        2
    )

    updated["ql_percent"] = round(
        ql_percent,
        2
    )

    updated["fta_profit"] = round(
        fta_profit,
        2
    )

    updated["expected_profit"] = round(
        expected_profit,
        2
    )

    updated["ev_percent"] = round(
        ev_percent,
        2
    )

    updated["ev_rating"] = round(
        ev_rating,
        2
    )

    return updated


def rank_opportunities(
    fixtures
):

    opportunities = []

    for fixture in fixtures:

        opportunity = (
            build_opportunity(
                fixture
            )
        )

        if opportunity:

            opportunities.append(
                opportunity
            )

    opportunities.sort(
        key=lambda x:
        x["ev_rating"],
        reverse=True
    )

    return opportunities


def get_top_opportunities(
    fixtures,
    limit=20
):

    ranked = (
        rank_opportunities(
            fixtures
        )
    )

    return ranked[:limit]
