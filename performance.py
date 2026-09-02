from database import (
    get_tracked_bets
)


def calculate_roi():

    bets = get_tracked_bets()

    if not bets:

        return 0

    total_staked = sum(
        bet[7] or 0
        for bet in bets
    )

    total_profit = sum(
    float(bet[15] or 0)
    if str(bet[15]).replace(".", "", 1).replace("-", "", 1).isdigit()
    else 0
    for bet in bets
)

    if total_staked == 0:

        return 0

    return round(
        (
            total_profit /
            total_staked
        ) * 100,
        2
    )
