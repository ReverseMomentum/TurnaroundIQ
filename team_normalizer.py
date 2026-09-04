from database import get_db


TEAM_ALIASES = {

    # Premier League

    "man utd":
        "Manchester United",

    "manchester utd":
        "Manchester United",

    "man united":
        "Manchester United",

    "man city":
        "Manchester City",

    "spurs":
        "Tottenham",

    "tottenham hotspur":
        "Tottenham",

    "newcastle utd":
        "Newcastle United",

    "wolves":
        "Wolverhampton Wanderers",

    "brighton":
        "Brighton and Hove Albion",

    "west ham":
        "West Ham United",

    "nottm forest":
        "Nottingham Forest",

    "notts forest":
        "Nottingham Forest",

    # Championship

    "qpr":
        "Queens Park Rangers",

    "boro":
        "Middlesbrough",

    "west brom":
        "West Bromwich Albion",

    "sheff utd":
        "Sheffield United",

    "sheff wed":
        "Sheffield Wednesday",

    "blackburn":
        "Blackburn Rovers",

    "preston":
        "Preston North End",

    "stoke":
        "Stoke City",

    "norwich":
        "Norwich City",

    "leicester":
        "Leicester City",

    "ipswich":
        "Ipswich Town",

    "swansea":
        "Swansea City",

    "cardiff":
        "Cardiff City",

    "birmingham":
        "Birmingham City",

    "hull":
        "Hull City",

    "coventry":
        "Coventry City",

    "bristol city":
        "Bristol City",

    # Scotland

    "hibs":
        "Hibernian",

    "hibernian fc":
        "Hibernian",

    "rangers":
        "Rangers",

    "glasgow rangers":
        "Rangers",

    "heart of midlothian":
        "Heart of Midlothian",

    "hearts fc":
        "Heart of Midlothian",

    "aberdeen fc":
        "Aberdeen",

    "dundee utd":
        "Dundee United",

    "dundee united fc":
        "Dundee United",

    "st mirren fc":
        "St Mirren",

    "motherwell fc":
        "Motherwell",

    "killie":
        "Kilmarnock",

    "kilmarnock fc":
        "Kilmarnock",

    # Portugal

    "sporting":
        "Sporting CP",

    "sporting lisbon":
        "Sporting CP",

    "sporting clube de portugal":
        "Sporting CP",

    "porto":
        "FC Porto",

    "fc porto":
        "FC Porto",

    "benfica":
        "Benfica",

    "sl benfica":
        "Benfica",

    "braga":
        "SC Braga",

    "sc braga":
        "SC Braga",


    # Germany

    "bayern":
        "Bayern Munich",

    "bayern munchen":
        "Bayern Munich",

    "bayern münchen":
        "Bayern Munich",

    "dortmund":
        "Borussia Dortmund",

    "gladbach":
        "Borussia Monchengladbach",

    "mgladbach":
        "Borussia Monchengladbach",

    "koln":
        "FC Koln",

    "köln":
        "FC Koln",

    # Spain

    "real madrid cf":
        "Real Madrid",

    "barcelona":
        "Barcelona",

    "fc barcelona":
        "Barcelona",

    "atletico":
        "Atletico Madrid",

    "atletico madrid":
        "Atletico Madrid",

    # Italy

    "inter":
        "Inter Milan",

    "internazionale":
        "Inter Milan",

    "ac milan":
        "AC Milan",

    "juve":
        "Juventus",

    # France

    "psg":
        "Paris Saint Germain",

    "paris sg":
        "Paris Saint Germain"

    # Belgium

    "club brugge":
        "Club Brugge",

    "club brugge kv":
        "Club Brugge",

    "royal antwerp":
        "Royal Antwerp",

    "antwerp":
        "Royal Antwerp",

    "anderlecht":
        "RSC Anderlecht",

    "rsc anderlecht":
        "RSC Anderlecht",

    "genk":
        "Genk",

    "krc genk":
        "Genk",

    "gent":
        "Gent",

    "kaa gent":
        "Gent",

    # Netherlands

    "psv":
        "PSV Eindhoven",

    "psv eindhoven":
        "PSV Eindhoven",

    "ajax amsterdam":
        "Ajax",

    "afc ajax":
        "Ajax",

    "feyenoord rotterdam":
        "Feyenoord",

    "az":
        "AZ Alkmaar",

    "az alkmaar":
        "AZ Alkmaar",

    "twente":
        "FC Twente",

    "fc twente":
        "FC Twente",

    # Denmark

    "fc copenhagen":
        "FC Copenhagen",

    "copenhagen":
        "FC Copenhagen",

    "kobenhavn":
        "FC Copenhagen",

    "københavn":
        "FC Copenhagen",

    "brondby":
        "Brondby",

    "brøndby":
        "Brondby",

    "midtjylland":
        "FC Midtjylland",

    "fc midtjylland":
        "FC Midtjylland",

    # Norway

    "bodo glimt":
        "Bodo/Glimt",

    "bodo/glimt":
        "Bodo/Glimt",

    "molde fk":
        "Molde",

    "rosenborg bk":
        "Rosenborg",

    "viking fk":
        "Viking",

    # Sweden

    "malmo":
        "Malmo FF",

    "malmö":
        "Malmo FF",

    "malmo ff":
        "Malmo FF",

    "aik stockholm":
        "AIK",

    "ifk goteborg":
        "IFK Goteborg",

    "ifk göteborg":
        "IFK Goteborg",

    "djurgardens":
        "Djurgardens IF",

    "djurgårdens":
        "Djurgardens IF",

    # MLS

    "lafc":
        "Los Angeles FC",

    "la fc":
        "Los Angeles FC",

    "inter miami":
        "Inter Miami CF",

    "atlanta":
        "Atlanta United",

    "atlanta utd":
        "Atlanta United",

    "nycfc":
        "New York City FC",

    "new york city":
        "New York City FC",

    "sporting kansas":
        "Sporting Kansas City",

    "sporting kc":
        "Sporting Kansas City",

    "st louis city":
        "St Louis City SC",


}


# In-process cache of the team_aliases table. Previously,
# get_alias_from_db() opened a brand-new sqlite connection on
# every single call - and normalize_team() is called twice per
# fixture across results_collector.py, build_training_data.py,
# odds_collector.py, etc. For a single script run that's still
# one process, so we only need to load the table once and reuse
# it, instead of one connection per team-name lookup.
_alias_cache = None
_alias_cache_loaded = False


def _load_alias_cache():

    global _alias_cache
    global _alias_cache_loaded

    cache = {}

    try:

        conn = get_db()

        rows = conn.execute(
            """
            SELECT alias, canonical_name
            FROM team_aliases
            """
        ).fetchall()

        conn.close()

        for alias, canonical_name in rows:

            cache[alias.lower()] = canonical_name

    except Exception:

        # table may not exist yet on a fresh DB - that's fine,
        # just means no DB-sourced aliases this run
        pass

    _alias_cache = cache
    _alias_cache_loaded = True


def reload_alias_cache():
    """
    Force a re-read of team_aliases from the DB. Call this if
    aliases were added mid-process (e.g. a long-running app
    server where an admin just added a new alias) - normal
    short-lived scripts (cron jobs) don't need to call this,
    the cache naturally refreshes on the next process start.
    """

    _load_alias_cache()


def clean_team_name(
    team_name
):
    """
    Standardise formatting.
    """

    if team_name is None:
        return ""

    team_name = str(team_name)

    team_name = (
        team_name
        .replace(".", "")
        .replace("-", " ")
        .replace("&", "and")
        .strip()
    )

    team_name = " ".join(
        team_name.split()
    )

    return team_name


def get_alias_from_db(
    team_name
):
    """
    Check team_aliases table (in-process cached).
    """

    if not _alias_cache_loaded:

        _load_alias_cache()

    return _alias_cache.get(
        team_name.lower()
    )


def normalize_team(
    team_name
):
    """
    Convert any team name
    into canonical form.
    """

    team_name = clean_team_name(
        team_name
    )

    if not team_name:
        return ""

    db_match = get_alias_from_db(
        team_name
    )

    if db_match:
        return db_match

    alias_match = TEAM_ALIASES.get(
        team_name.lower()
    )

    if alias_match:
        return alias_match

    return team_name


def teams_match(
    team_a,
    team_b
):
    """
    Compare two team names.
    """

    return (
        normalize_team(team_a)
        ==
        normalize_team(team_b)
    )


def normalize_fixture(
    home_team,
    away_team
):
    """
    Returns tuple of normalized teams.
    """

    return (
        normalize_team(
            home_team
        ),
        normalize_team(
            away_team
        )
    )


if __name__ == "__main__":

    samples = [

        "Man Utd",

        "Manchester United",

        "Spurs",

        "Tottenham Hotspur",

        "QPR",

        "Bayern München",

        "PSG"

    ]

    for team in samples:

        print(
            team,
            "->",
            normalize_team(team)
        )
