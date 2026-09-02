import pandas as pd

CSV_FILE = (
    "data/2up_multi_league_dataset.csv"
)


def build_league_stats():

    df = pd.read_csv(
        CSV_FILE
    )

    league_rows = []

    for league in (
        df["league"]
        .dropna()
        .unique()
    ):

        league_df = df[
            df["league"] == league
        ]

        matches = len(
            league_df
        )

        two_up = len(
            league_df[
                league_df[
                    "2up_triggered"
                ] == True
            ]
        )

        comebacks = len(
            league_df[
                league_df[
                    "comeback_occurred"
                ] == True
            ]
        )

        trigger_rate = 0

        if matches > 0:
            trigger_rate = (
                two_up
                / matches
            ) * 100

        turnaround_rate = 0

        if two_up > 0:
            turnaround_rate = (
                comebacks
                / two_up
            ) * 100

        league_rows.append(
            {
                "league": league,
                "matches": matches,
                "two_up": two_up,
                "comebacks": comebacks,
                "trigger_rate":
                    round(
                        trigger_rate,
                        2
                    ),
                "turnaround_rate":
                    round(
                        turnaround_rate,
                        2
                    )
            }
        )

    return pd.DataFrame(
        league_rows
    )


if __name__ == "__main__":

    df = (
        build_league_stats()
    )

    df.to_csv(
        "data/league_stats.csv",
        index=False
    )

    print(
        "league_stats.csv created"
    )
