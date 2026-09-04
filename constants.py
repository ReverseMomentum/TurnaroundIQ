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

# API-Football league IDs used only by results_collector.
SUPPORTED_LEAGUE_IDS = {
    39: "Premier League",
    40: "Championship",
    41: "League One",
    42: "League Two",
    179: "Premiership",
    78: "Bundesliga",
    79: "2. Bundesliga",
    140: "La Liga",
    135: "Serie A",
    61: "Ligue 1",
    88: "Eredivisie",
    144: "Jupiler Pro League",
    94: "Primeira Liga",
    253: "Major League Soccer",
    119: "Superliga",
    103: "Eliteserien",
    113: "Allsvenskan",
    357: "Premier Division",
}

SUPPORTED_LEAGUES = list(SUPPORTED_LEAGUE_IDS.values())

SAMPLE_WEIGHT_HALF_LIFE_YEARS = 2.0
SAMPLE_WEIGHT_FLOOR = 0.05

# TheStatsAPI — xG + pre-match back odds.
THESTATSAPI_KEY = "fapi_aGYmBLcFZ7tLylMXENrK62GkYxlnEEiq"
THESTATSAPI_PREFERRED_BOOKS = [
    "Bet365",
    "Pinnacle",
    "Paddy Power",
    "Betfair Sportsbook",
    "Kambi",
]
