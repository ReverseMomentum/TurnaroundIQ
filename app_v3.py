import pandas as pd
import streamlit as st
import subprocess
import sys
import matplotlib.pyplot as plt
import uuid


from datetime import datetime

from database import (
    get_latest_odds,
    get_tracked_bets,
    get_performance_stats,
    save_tracked_bet
)

from calculations import (
    calculate_lay_stake,
    calculate_liability,
    calculate_qualifying_loss,
    calculate_fta_profit,
    calculate_expected_profit,
    calculate_ev_percent,
    calculate_roi,
    calculate_win_rate
)

from database import (
    get_latest_odds,
    get_tracked_bets,
    get_performance_stats
)

from models.opportunities_engine import (
    build_opportunity,
    rebuild_opportunity
)

# ==================================
# PAGE CONFIG
# ==================================

st.set_page_config(
    page_title="2UP Master V3",
    page_icon="⚽",
    layout="wide"
)

# ==================================
# HEADER
# ==================================

st.title(
    "⚽ 2UP Master V3"
)

st.caption(
    "Machine Learning Powered 2UP Opportunity Discovery & Tracking Platform"
)

# ==================================
# TABS
# ==================================

tab_opps, tab_tracking, tab_calc, tab_perf, tab_admin = st.tabs(
    [
        "⚡ Opportunities",
        "📌 Tracking",
        "🧮 Calculator",
        "📈 Performance",
        "⚙️ Admin"
    ]
)

# ==================================
# OPPORTUNITIES
# ==================================

with tab_opps:

    st.header(
        "⚡ Opportunities"
    )

    rows = get_latest_odds()

    if not rows:

        st.warning(
            "No odds available. Run odds_collector.py first."
        )

    else:

        fixtures = []

        for row in rows:

            fixture = {

                "match":
                    f"{row[3]} v {row[4]}",

                "team":
                    row[5],

                "league":
                    row[2],

                "bookmaker":
                    row[6],

                "back_odds":
                    float(
                        row[7]
                    ),

                "is_home":
                    (
                        row[5]
                        ==
                        row[3]
                    )
            }

            fixtures.append(
                fixture
            )

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
            x["ranking_score"],
            reverse=True
        )

        st.success(
            f"{len(opportunities)} opportunities found"
        )

        for i, opp in enumerate(
            opportunities[:50]
        ):

            title = (
                f"{opp['match']} | "
                f"{opp['bookmaker']} | "
                f"EV {opp['ev_percent']}%"
            )

            with st.expander(
                title
            ):

                st.write(
                    f"**Team:** {opp['team']}"
                )

                st.write(
                    f"**League:** {opp['league']}"
                )

                st.write(
                    f"**Bookmaker:** {opp['bookmaker']}"
                )

                st.write(
                    f"**Back Odds:** {opp['back_odds']}"
                )

                if opp[
                    "estimated_lay"
                ]:

                    st.warning(
                        "Estimated Lay Odds"
                    )

                else:

                    st.success(
                        "Confirmed Lay Odds"
                    )

                lay_odds = st.number_input(
                    "Lay Odds",
                    min_value=1.01,
                    value=float(
                        opp[
                            "lay_odds"
                        ]
                    ),
                    key=f"lay_{i}"
                )

                commission = st.number_input(
                    "Commission %",
                    min_value=0.0,
                    max_value=10.0,
                    value=float(
                        opp[
                            "commission"
                        ]
                    ),
                    step=0.5,
                    key=f"comm_{i}"
                )

                updated = (
                    rebuild_opportunity(
                        opp,
                        lay_odds,
                        commission
                    )
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "FTA %",
                    updated[
                        "fta_pct"
                    ]
                )

                c2.metric(
                    "Expected Profit",
                    f"£{updated['expected_profit']}"
                )

                c3.metric(
                    "EV %",
                    f"{updated['ev_percent']}%"
                )

                c1.metric(
                    "Lay Stake",
                    f"£{updated['lay_stake']}"
                )

                c2.metric(
                    "Liability",
                    f"£{updated['liability']}"
                )

                c3.metric(
                    "Qualifying Loss",
                    f"£{updated['qualifying_loss']}"
                )
                if st.button(
                    "📌 Track Bet",
                    key=f"track_{i}"
                ):

                    bet_data = {

                        "id":
                            str(
                                uuid.uuid4()
                            ),

                        "match_name":
                            updated[
                                "match"
                            ],

                        "team":
                            updated[
                                "team"
                            ],

                        "league":
                            updated[
                                "league"
                            ],

                        "kickoff":
                            "",

                        "bookmaker":
                            updated[
                                "bookmaker"
                            ],

                        "back_odds":
                            updated[
                                "back_odds"
                            ],

                        "lay_odds":
                            updated[
                                "lay_odds"
                            ],

                        "estimated_lay":
                            int(
                                updated[
                                    "estimated_lay"
                                ]
                            ),

                        "stake":
                            updated[
                                "stake"
                            ],

                        "commission":
                            updated[
                                "commission"
                            ],

                        "lay_stake":
                            updated[
                                "lay_stake"
                            ],

                        "liability":
                            updated[
                                "liability"
                            ],

                        "qualifying_loss":
                            updated[
                                "qualifying_loss"
                            ],

                        "outcome_fta":
                            updated[
                                "fta_profit"
                            ],

                        "fta_pct":
                            updated[
                                "fta_pct"
                            ],

                        "ev_pct":
                            updated[
                                "ev_percent"
                            ],

                        "expected_profit":
                            updated[
                                "expected_profit"
                            ],

                        "actual_profit":
                            None,

                        "actual_fta":
                            None,

                        "status":
                            "Pending",

                        "result":
                            None,

                        "model_version":
                            "V3",

                        "created_at":
                            datetime.now().isoformat(),

                        "settled_at":
                            None
                    }

                    save_tracked_bet(
                        bet_data
                    )

                    st.success(
                        "Bet tracked successfully."
                    )



# ==================================
# TRACKING
# ==================================

with tab_tracking:

    st.header(
        "📌 Tracked Bets"
    )

    bets = get_tracked_bets()

    if bets:

        columns = [

    "id",

    "match_name",
    "team",
    "league",
    "kickoff",

    "bookmaker",

    "back_odds",
    "lay_odds",

    "estimated_lay",

    "stake",
    "commission",

    "lay_stake",
    "liability",

    "qualifying_loss",
    "outcome_fta",

    "fta_pct",
    "ev_pct",

    "expected_profit",
    "actual_profit",

    "actual_fta",

    "status",
    "result",

    "model_version",

    "created_at",
    "settled_at"
]
        

        df = pd.DataFrame(
            bets,
            columns=columns
        )

        st.dataframe(
            df,
            use_container_width=True
        )

    else:

        st.info(
            "No tracked bets found."
        )

# ==================================
# CALCULATOR
# ==================================

with tab_calc:

    st.header(
        "🧮 2UP Calculator"
    )

    col1, col2 = st.columns(2)

    with col1:

        back_odds = st.number_input(
            "Back Odds",
            min_value=1.01,
            value=4.60
        )

        lay_odds = st.number_input(
            "Lay Odds",
            min_value=1.01,
            value=5.00
        )

        stake = st.number_input(
            "Stake (£)",
            min_value=1.0,
            value=40.0
        )

        commission = st.number_input(
            "Commission",
            min_value=0.0,
            value=2.0
        )

        fta_pct = st.number_input(
            "FTA %",
            min_value=0.0,
            value=2.53
        )

    lay_stake = calculate_lay_stake(
        back_odds,
        lay_odds,
        stake,
        commission
    )

    liability = calculate_liability(
        lay_odds,
        lay_stake
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

    with col2:

        st.metric(
            "Lay Stake",
            f"£{lay_stake:.2f}"
        )

        st.metric(
            "Liability",
            f"£{liability:.2f}"
        )

        st.metric(
            "Qualifying Loss",
            f"£{qualifying_loss:.2f}"
        )

        st.metric(
            "FTA Profit",
            f"£{fta_profit:.2f}"
        )

        st.metric(
            "Expected Profit",
            f"£{expected_profit:.2f}"
        )

        st.metric(
            "EV %",
            f"{ev_percent:.2f}%"
        )

# ==================================
# PERFORMANCE
# ==================================

with tab_perf:

    st.header(
        "📈 Performance"
    )

    total_bets, expected_profit, actual_profit = (
        get_performance_stats()
    )

    tracked_bets = (
        get_tracked_bets()
    )

    won_bets = 0
    lost_bets = 0

    total_staked = 0

    for row in tracked_bets:

        stake = row[9]
        profit = row[18]

        if profit is not None:

            total_staked += (
                stake or 0
            )

            if profit > 0:
                won_bets += 1

            elif profit < 0:
                lost_bets += 1

    roi = calculate_roi(
        actual_profit,
        total_staked
    )

    win_rate = calculate_win_rate(
        won_bets,
        lost_bets
    )

    p1, p2, p3 = st.columns(3)

    p1.metric(
        "Total Bets",
        total_bets
    )

    p2.metric(
        "Expected Profit",
        f"£{expected_profit:.2f}"
    )

    p3.metric(
        "Actual Profit",
        f"£{actual_profit:.2f}"
    )

    p1.metric(
        "ROI %",
        f"{roi:.2f}%"
    )

    p2.metric(
        "Win Rate %",
        f"{win_rate:.2f}%"
    )

    p3.metric(
        "Won / Lost",
        f"{won_bets}/{lost_bets}"
    )

    st.markdown("---")

    st.subheader(
        "📈 Expected Profit vs Actual Profit"
    )

    expected_running = 0
    actual_running = 0

    expected_curve = []
    actual_curve = []

    settled_count = []

    counter = 0

    for row in tracked_bets:

        expected_profit_row = row[17]
        actual_profit_row = row[18]

        if actual_profit_row is None:
            continue

        counter += 1

        expected_running += (
            expected_profit_row or 0
        )

        actual_running += (
            actual_profit_row or 0
        )

        settled_count.append(
            counter
        )

        expected_curve.append(
            expected_running
        )

        actual_curve.append(
            actual_running
        )

    if expected_curve:

        variance = (
            actual_running -
            expected_running
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Expected Total",
            f"£{expected_running:.2f}"
        )

        c2.metric(
            "Actual Total",
            f"£{actual_running:.2f}"
        )

        c3.metric(
            "Variance",
            f"£{variance:.2f}"
        )

        fig, ax = plt.subplots(
            figsize=(12, 6)
        )

        ax.plot(
            settled_count,
            expected_curve,
            color="blue",
            linewidth=2,
            label="Expected Profit"
        )

        ax.plot(
            settled_count,
            actual_curve,
            color="green",
            linewidth=2,
            label="Actual Profit"
        )

        ax.axhline(
            y=0,
            color="grey",
            linestyle="--"
        )

        ax.set_title(
            "Cumulative Expected vs Actual Profit"
        )

        ax.set_xlabel(
            "Settled Bets"
        )

        ax.set_ylabel(
            "Profit (£)"
        )

        ax.legend()

        ax.grid(
            True,
            alpha=0.3
        )

        st.pyplot(fig)


# ==================================
# ADMIN
# ==================================

with tab_admin:

    st.header(
        "⚙️ Admin"
    )

    st.subheader(
        "Data Collection"
    )

    if st.button(
        "🔄 Refresh Odds"
    ):

        with st.spinner(
            "Collecting OddsPapi data..."
        ):

            try:

                subprocess.run(
                    [
                        sys.executable,
                        "collectors/odds_collector.py"
                    ],
                    check=True
                )

                st.success(
                    "Odds refreshed successfully."
                )

            except Exception as exc:

                st.error(
                    str(exc)
                )

    st.markdown("---")

    st.subheader(
        "Machine Learning"
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "📊 Update Team Stats"
        ):

            try:

                subprocess.run(
                    [
                        sys.executable,
                        "collectors/update_turnaround_stats.py"
                    ],
                    check=True
                )

                st.success(
                    "Team stats updated."
                )

            except Exception as exc:

                st.error(
                    str(exc)
                )

        if st.button(
            "🏗 Build Training Data"
        ):

            try:

                subprocess.run(
                    [
                        sys.executable,
                        "training/build_training_data.py"
                    ],
                    check=True
                )

                st.success(
                    "Training data rebuilt."
                )

            except Exception as exc:

                st.error(
                    str(exc)
                )

    with col2:

        if st.button(
            "🤖 Retrain Model"
        ):

            try:

                subprocess.run(
                    [
                        sys.executable,
                        "models/retrain_model.py"
                    ],
                    check=True
                )

                st.success(
                    "Model retrained."
                )

            except Exception as exc:

                st.error(
                    str(exc)
                )

    st.markdown("---")

    st.subheader(
        "Full Refresh Pipeline"
    )

    if st.button(
        "🚀 Full Refresh"
    ):

        progress_bar = st.progress(0)

        status = st.empty()

        try:

            steps = [

                (
                    "Refreshing Odds",
                    "collectors/odds_collector.py"
                ),

                (
                    "Updating Team Stats",
                    "collectors/update_turnaround_stats.py"
                ),

                (
                    "Building Training Data",
                    "training/build_training_data.py"
                ),

                (
                    "Retraining Model",
                    "models/retrain_model.py"
                )
            ]

            total_steps = len(
                steps
            )

            for index, (
                step_name,
                script
            ) in enumerate(
                steps
            ):

                status.info(
                    f"Running: {step_name}"
                )

                subprocess.run(
                    [
                        sys.executable,
                        script
                    ],
                    check=True
                )

                progress_bar.progress(
                    int(
                        (
                            index + 1
                        )
                        /
                        total_steps
                        * 100
                    )
                )

            status.success(
                "✅ Full refresh completed successfully."
            )

        except Exception as exc:

            status.error(
                f"❌ Failed: {exc}"
            )
