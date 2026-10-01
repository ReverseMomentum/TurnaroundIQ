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
    235: "Russian Premier League",
    136: "Serie B",
    62: "Ligue 2",
    203: "Super Lig",
    218: "Austrian Bundesliga",
    207: "Swiss Super League",
    71: "Brasileirao",
    # Youth (England, U21): ~1.4-1.5x the average turnaround rate in 2023-25
    # because far more games reach 2-up (scripts/league_scout.py probe).
    702: "Premier League 2",
    703: "Professional Development League",
}

SUPPORTED_LEAGUES = list(SUPPORTED_LEAGUE_IDS.values())

# Dixon–Coles inspired sample weights for training_data.
# weight = 0.5 ** (years_ago / half_life). 1.5y half-life ≈ ξ ≈ 0.00127 / day
# (recent seasons dominate; older path rates still present but soft).
SAMPLE_WEIGHT_HALF_LIFE_YEARS = 1.5
SAMPLE_WEIGHT_FLOOR = 0.05

# API keys come from the environment, never from git.
# Set them in /etc/turnaroundiq.env (systemd) or a repo-root .env (cron / CLI).
import os  # noqa: E402

import env_loader  # noqa: E402

env_loader.load()

# API-Football — results_collector + upcoming fixtures.
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()

# TheStatsAPI — xG + pre-match back odds.
THESTATSAPI_KEY = os.environ.get("THESTATSAPI_KEY", "").strip()
THESTATSAPI_PREFERRED_BOOKS = [
    "Bet365",
    "Pinnacle",
    "Paddy Power",
    "Betfair Sportsbook",
    "Kambi",
]
