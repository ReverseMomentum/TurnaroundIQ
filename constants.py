# NOTE: this previously didn't match the real tracked_bets
# schema in database.py at all (wrong columns, wrong order) -
# performance.py's calculate_roi() was silently reading the
# wrong fields as a result. Corrected to match database.py's
# CREATE TABLE tracked_bets exactly, in order.
BET_COLUMNS = [
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

# API-Football league IDs. Name matching is unsafe: several
# countries call their top flight "Premier League".
SUPPORTED_LEAGUE_IDS = {
    # England
    39: "Premier League",
    40: "Championship",
    41: "League One",
    42: "League Two",

    # Scotland
    179: "Premiership",

    # Germany
    78: "Bundesliga",
    79: "2. Bundesliga",

    # Spain
    140: "La Liga",

    # Italy
    135: "Serie A",

    # France
    61: "Ligue 1",

    # Netherlands
    88: "Eredivisie",

    # Belgium
    144: "Jupiler Pro League",

    # Portugal
    94: "Primeira Liga",

    # MLS
    253: "Major League Soccer",

    # Denmark
    119: "Superliga",

    # Norway
    103: "Eliteserien",

    # Sweden
    113: "Allsvenskan",

    # Ireland
    357: "Premier Division",
}

SUPPORTED_LEAGUES = list(SUPPORTED_LEAGUE_IDS.values())
