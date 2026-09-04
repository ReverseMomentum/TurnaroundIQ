def calculate_lay_stake(back_odds, lay_odds, stake, commission):
    """Equal-profit lay stake for a 2UP / FTA hedge."""
    denominator = lay_odds - (commission / 100)
    if denominator <= 0:
        return 0.0
    return round((back_odds * stake) / denominator, 2)


def calculate_liability(lay_odds, lay_stake):
    """Exchange liability if the lay loses."""
    return round((lay_odds - 1) * lay_stake, 2)


def calculate_qualifying_loss(
    back_odds,
    lay_odds,
    stake,
    lay_stake,
    commission,
):
    """
    Qualifying loss using the 2UP Master V3 formula.

    Bookmaker profit if the selection wins outright, minus exchange
    liability on the lay. Commission is already baked into lay_stake.
    """
    bookmaker_profit = stake * (back_odds - 1)
    liability = (lay_odds - 1) * lay_stake
    return round(bookmaker_profit - liability, 2)


def calculate_fta_profit(stake, back_odds, lay_stake, commission):
    """Profit if the team goes 2 goals ahead and then fails to win."""
    bookmaker_return = stake * back_odds
    lay_win = lay_stake * (1 - (commission / 100))
    return round(bookmaker_return + lay_win - stake, 2)


def calculate_expected_profit(fta_profit, qualifying_loss, fta_pct):
    """Probability-weighted expected profit."""
    probability = fta_pct / 100
    return round(
        (fta_profit * probability)
        - (abs(qualifying_loss) * (1 - probability)),
        2,
    )


def calculate_ev_percent(expected_profit, qualifying_loss):
    """
    EV as a percentage of money at risk (qualifying loss).

    This is the function imported by app_v3.py and
    models/opportunities_engine.py:

        calculate_ev_percent(expected_profit, qualifying_loss)

    0 means break-even expected value.
    Positive means expected profit relative to QL.
    """
    risk = abs(qualifying_loss)
    if risk <= 0:
        return 0.0
    return round((expected_profit / risk) * 100, 2)


def calculate_ev_pct(fta_pct, qualifying_loss, fta_profit):
    """
    EV score versus the break-even FTA rate.

    100 = break-even
    >100 = positive edge
    <100 = negative edge
    """
    total_risk = abs(qualifying_loss) + fta_profit
    if total_risk <= 0:
        return 0.0

    break_even_pct = (abs(qualifying_loss) / total_risk) * 100
    if break_even_pct <= 0:
        return 0.0

    return round((fta_pct / break_even_pct) * 100, 1)


def calculate_ev_rating(fta_pct, qualifying_loss, stake):
    """
    EV rating versus qualifying loss as a percentage of stake.

    100% means FTA % == QL % of stake.
    """
    if stake <= 0:
        return 0.0

    ql_percent = (abs(qualifying_loss) / stake) * 100
    if ql_percent <= 0:
        return 0.0

    return round((fta_pct / ql_percent) * 100, 2)


def calculate_ranking_score(expected_profit, fta_pct, xg_edge=0):
    """
    Sort key for opportunity lists.

    xg_edge is optional so this can replace both copies
    (calculations.py and models/model.py).
    """
    return round(
        (expected_profit * (fta_pct / 100)) + (xg_edge * 0.1),
        4,
    )


def calculate_roi(actual_profit, total_staked):
    """Return on investment for settled bets."""
    if not total_staked:
        return 0.0
    return round((actual_profit / total_staked) * 100, 2)


def calculate_win_rate(won_bets, lost_bets):
    """Win percentage of settled bets with a non-zero P/L."""
    total = won_bets + lost_bets
    if total == 0:
        return 0.0
    return round((won_bets / total) * 100, 2)
