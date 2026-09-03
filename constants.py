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

SUPPORTED_LEAGUES = [

    # England

    "Premier League",
    "Championship",
    "League One",
    "League Two",

    # Scotland
    # NOTE: API-Football's own historical announcements refer
    # to this competition as just "Premiership" (see their
    # 2018 news archive: "SCOTLAND Premiership 2018/2019"),
    # not "Scottish Premiership". Changed based on that - the
    # unmatched-league diagnostic in results_collector.py will
    # confirm on first live run; revert if it still shows up
    # there as unmatched.

    "Premiership",

    # Germany

    "Bundesliga",
    "2. Bundesliga",

    # Spain

    "La Liga",

    # Italy

    "Serie A",

    # France

    "Ligue 1",

    # Netherlands

    "Eredivisie",

    # Belgium
    # NOTE: same situation - API-Football's own archive refers
    # to this as "Jupiler Pro League", not "Belgian Pro League".
    # Same caveat as Scotland above.

    "Jupiler Pro League",

    # Portugal

    "Primeira Liga",

    # MLS

    "Major League Soccer",

    # Denmark

    "Superliga",

    # Norway

    "Eliteserien",

    # Sweden

    "Allsvenskan",

    # Ireland

    "Premier Division"
]
