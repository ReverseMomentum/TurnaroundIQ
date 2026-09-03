def calculate_lay_stake(
    back_odds,
    lay_odds,
    stake,
    commission
):
    """
    Calculate equal-profit lay stake.
    """

    return round(
        (
            back_odds * stake
        )
        /
        (
            lay_odds -
            (commission / 100)
        ),
        2
    )


def calculate_liability(
    lay_odds,
    lay_stake
):
    """
    Calculate exchange liability.
    """

    return round(
        (
            lay_odds - 1
        )
        * lay_stake,
        2
    )


def calculate_qualifying_loss(
    back_odds,
    lay_odds,
    stake,
    lay_stake,
    commission
):
    """
    Calculate qualifying loss using
    the 2UP Master V3 formula.
    """

    bookmaker_profit = (
        stake *
        (
            back_odds - 1
        )
    )

    liability = (
        lay_odds - 1
    ) * lay_stake

    return round(
        bookmaker_profit -
        liability,
        2
    )


def calculate_fta_profit(
    stake,
    back_odds,
    lay_stake,
    commission
):
    """
    Profit if team goes 2 goals ahead
    and fails to win.
    """

    bookmaker_return = (
        stake *
        back_odds
    )

    lay_win = (
        lay_stake *
        (
            1 -
            (
                commission / 100
            )
        )
    )

    return round(
        bookmaker_return +
        lay_win -
        stake,
        2
    )


def calculate_expected_profit(
    fta_profit,
    qualifying_loss,
    fta_pct
):
    """
    Expected value/profit.
    """

    probability = (
        fta_pct / 100
    )

    return round(
        (
            fta_profit *
            probability
        )
        -
        (
            abs(
                qualifying_loss
            )
            *
            (
                1 - probability
            )
        ),
        2
    )


def calculate_ev_pct(
    fta_pct,
    qualifying_loss,
    fta_profit
):
    """
    EV Score

    100 = break-even

    >100 = positive edge

    <100 = negative edge
    """

    total_risk = (
        abs(
            qualifying_loss
        )
        +
        fta_profit
    )

    if total_risk <= 0:

        return 0

    break_even_pct = (
        abs(
            qualifying_loss
        )
        /
        total_risk
    ) * 100

    if break_even_pct <= 0:

        return 0

    ev_score = (
        fta_pct
        /
        break_even_pct
    ) * 100

    return round(
        ev_score,
        1
    )



def calculate_roi(
    actual_profit,
    total_staked
):
    """
    Return on investment.
    """

    if total_staked == 0:
        return 0

    return round(
        (
            actual_profit
            /
            total_staked
        )
        * 100,
        2
    )


def calculate_win_rate(
    won_bets,
    lost_bets
):
    """
    Win percentage of settled bets.
    """

    total = (
        won_bets +
        lost_bets
    )

    if total == 0:
        return 0

    return round(
        (
            won_bets /
            total
        )
        * 100,
        2
    )

def calculate_ev_rating(
    fta_pct,
    qualifying_loss,
    stake
):
    """
    EV Rating

    100% means:

    FTA %
    ==
    Qualifying Loss %

    >100%
    Better

    <100%
    Worse
    """

    if stake <= 0:
        return 0

    ql_percent = (
        abs(
            qualifying_loss
        )
        /
        stake
    ) * 100

    if ql_percent <= 0:
        return 0

    return round(
        (
            fta_pct
            /
            ql_percent
        )
        * 100,
        2
    )


def calculate_ranking_score(
    expected_profit,
    fta_pct
):
    """
    Opportunity ranking score.
    Used for sorting opportunities.
    """

    return round(
        expected_profit
        *
        (
            fta_pct / 100
        ),
        4
    )
