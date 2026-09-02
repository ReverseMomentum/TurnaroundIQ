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

    "celtic fc":
        "Celtic",

    "rangers fc":
        "Rangers",

    "hearts":
        "Heart of Midlothian",

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
}


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
    Check team_aliases table.
    """

    try:

        conn = get_db()

        row = conn.execute(
            """
            SELECT canonical_name
            FROM team_aliases
            WHERE LOWER(alias) = ?
            """,
            (
                team_name.lower(),
            )
        ).fetchone()

        conn.close()

        if row:
            return row[0]

    except Exception:
        pass

    return None


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
