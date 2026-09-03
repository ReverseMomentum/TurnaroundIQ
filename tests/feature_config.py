"""
Canonical feature list for the FTA model.

This is imported by retrain_model.py (training), model.py
(live prediction), and backtest.py (historical simulation).

Do NOT maintain separate copies of this list in those files -
that's exactly how max_lead/odds_movement ended up trained-on
but never actually built into the live feature vector. One
list, three importers.
"""

FEATURE_COLUMNS = [

    # Team quality / form
    "avg_xg",
    "avg_xga",
    "xg_edge",

    "goals_last5",
    "conceded_last5",

    # Historical (all-time API-collected) turnaround signal
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

    # Context
    "league_turnaround_rate",
    "opponent_turnaround_rate",

    # Live (recent-form) behavioural rates
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

    # Historical vs live divergence
    "trigger_rate_delta",
    "early_goal_delta",
    "early_concede_delta",
    "first_lead_delta",
    "first_concede_delta",
    "comeback_delta",
    "lead_retention_delta",
    "burnout_delta",

    "abs_trigger_delta",
    "abs_retention_delta",

    # Match context
    "is_home",

    "lead_minute",
    "max_lead",

    "opening_back_odds",
    "odds_movement",

    "red_cards_for",
    "red_cards_against",

    "shots_for",
    "shots_against"
]
