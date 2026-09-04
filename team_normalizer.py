import difflib
import unicodedata
from datetime import datetime, timezone

from database import get_db


TEAM_ALIASES = {

    "man utd": "Manchester United",
    "manchester utd": "Manchester United",
    "man united": "Manchester United",
    "man city": "Manchester City",
    "spurs": "Tottenham",
    "tottenham hotspur": "Tottenham",
    "newcastle utd": "Newcastle United",
    "wolves": "Wolverhampton Wanderers",
    "brighton": "Brighton and Hove Albion",
    "west ham": "West Ham United",
    "nottm forest": "Nottingham Forest",
    "notts forest": "Nottingham Forest",
    "qpr": "Queens Park Rangers",
    "boro": "Middlesbrough",
    "west brom": "West Bromwich Albion",
    "sheff utd": "Sheffield United",
    "sheff wed": "Sheffield Wednesday",
    "blackburn": "Blackburn Rovers",
    "preston": "Preston North End",
    "stoke": "Stoke City",
    "norwich": "Norwich City",
    "leicester": "Leicester City",
    "ipswich": "Ipswich Town",
    "swansea": "Swansea City",
    "cardiff": "Cardiff City",
    "birmingham": "Birmingham City",
    "hull": "Hull City",
    "coventry": "Coventry City",
    "bristol city": "Bristol City",
    "hibs": "Hibernian",
    "hibernian fc": "Hibernian",
    "rangers": "Rangers",
    "glasgow rangers": "Rangers",
    "heart of midlothian": "Heart Of Midlothian",
    "hearts": "Heart Of Midlothian",
    "hearts fc": "Heart of Midlothian",
    "aberdeen fc": "Aberdeen",
    "dundee utd": "Dundee United",
    "dundee united fc": "Dundee United",
    "st mirren fc": "St Mirren",
    "motherwell fc": "Motherwell",
    "killie": "Kilmarnock",
    "kilmarnock fc": "Kilmarnock",
    "sporting": "Sporting CP",
    "sporting lisbon": "Sporting CP",
    "sporting clube de portugal": "Sporting CP",
    "porto": "FC Porto",
    "fc porto": "FC Porto",
    "benfica": "Benfica",
    "sl benfica": "Benfica",
    "braga": "SC Braga",
    "sc braga": "SC Braga",
    "bayern": "Bayern Munich",
    "bayern munchen": "Bayern Munich",
    "bayern münchen": "Bayern Munich",
    "dortmund": "Borussia Dortmund",
    "gladbach": "Borussia Monchengladbach",
    "mgladbach": "Borussia Monchengladbach",
    "koln": "FC Koln",
    "köln": "FC Koln",
    "1 fc koln": "FC Koln",
    "1 fc köln": "FC Koln",
    "real madrid cf": "Real Madrid",
    "barcelona": "Barcelona",
    "fc barcelona": "Barcelona",
    "atletico": "Atletico Madrid",
    "atletico madrid": "Atletico Madrid",
    "inter": "Inter Milan",
    "internazionale": "Inter Milan",
    "ac milan": "AC Milan",
    "juve": "Juventus",
    "psg": "Paris Saint Germain",
    "paris sg": "Paris Saint Germain",
    "club brugge": "Club Brugge",
    "club brugge kv": "Club Brugge",
    "royal antwerp": "Royal Antwerp",
    "antwerp": "Royal Antwerp",
    "anderlecht": "Anderlecht",
    "rsc anderlecht": "Anderlecht",
    "genk": "Genk",
    "krc genk": "Genk",
    "gent": "Gent",
    "kaa gent": "Gent",
    "psv": "PSV Eindhoven",
    "psv eindhoven": "PSV Eindhoven",
    "ajax amsterdam": "Ajax",
    "afc ajax": "Ajax",
    "feyenoord rotterdam": "Feyenoord",
    "az": "AZ Alkmaar",
    "az alkmaar": "AZ Alkmaar",
    "twente": "FC Twente",
    "fc twente": "FC Twente",
    "fc copenhagen": "FC Copenhagen",
    "copenhagen": "FC Copenhagen",
    "kobenhavn": "FC Copenhagen",
    "københavn": "FC Copenhagen",
    "brondby": "Brondby",
    "brøndby": "Brondby",
    "midtjylland": "FC Midtjylland",
    "fc midtjylland": "FC Midtjylland",
    "bodo glimt": "Bodo/Glimt",
    "bodo/glimt": "Bodo/Glimt",
    "molde fk": "Molde",
    "rosenborg bk": "Rosenborg",
    "viking fk": "Viking",
    "malmo": "Malmo FF",
    "malmö": "Malmo FF",
    "malmo ff": "Malmo FF",
    "aik stockholm": "AIK",
    "ifk goteborg": "IFK Goteborg",
    "ifk göteborg": "IFK Goteborg",
    "djurgardens": "Djurgardens IF",
    "djurgårdens": "Djurgardens IF",
    "lafc": "Los Angeles FC",
    "la fc": "Los Angeles FC",
    "inter miami": "Inter Miami CF",
    "atlanta": "Atlanta United",
    "atlanta utd": "Atlanta United",
    "nycfc": "New York City FC",
    "new york city": "New York City FC",
    "sporting kansas": "Sporting Kansas City",
    "sporting kc": "Sporting Kansas City",
    "st louis city": "St Louis City SC",
}

_PREFIXES = (
    "1 fc ", "1 ", "fc ", "afc ", "sc ", "sv ", "as ", "ac ",
    "fk ", "if ", "bk ", "sk ", "rc ", "rsc ", "krc ", "kaa ",
    "sl ", "cf ", "cd ", "ud ", "ss ", "us ", "tsg ",
)

_alias_cache = None
_alias_cache_loaded = False
_team_stats_cache = None


def _strip_accents(text):
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def _load_alias_cache():
    global _alias_cache, _alias_cache_loaded
    cache = {}
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT alias, canonical_name FROM team_aliases"
        ).fetchall()
        conn.close()
        for alias, canonical_name in rows:
            cache[alias.lower()] = canonical_name
    except Exception:
        pass
    _alias_cache = cache
    _alias_cache_loaded = True


def reload_alias_cache():
    _load_alias_cache()


def clean_team_name(team_name):
    if team_name is None:
        return ""
    team_name = str(team_name)
    team_name = (
        team_name.replace(".", " ")
        .replace("-", " ")
        .replace("&", "and")
        .strip()
    )
    team_name = " ".join(team_name.split())
    return team_name


def get_alias_from_db(team_name):
    if not _alias_cache_loaded:
        _load_alias_cache()
    return _alias_cache.get(team_name.lower())


def normalize_team(team_name):
    team_name = clean_team_name(team_name)
    if not team_name:
        return ""
    db_match = get_alias_from_db(team_name)
    if db_match:
        return db_match
    alias_match = TEAM_ALIASES.get(team_name.lower())
    if alias_match:
        return alias_match
    return team_name


def match_key(team_name):
    text = _strip_accents(clean_team_name(team_name)).lower()
    text = text.replace("/", " ")
    text = " ".join(text.split())
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                changed = True
                break
    if text.endswith(" fc"):
        text = text[:-3]
    return text.strip()


def load_team_stats_names():
    global _team_stats_cache
    if _team_stats_cache is not None:
        return _team_stats_cache
    conn = get_db()
    rows = conn.execute("SELECT team FROM team_stats").fetchall()
    conn.close()
    _team_stats_cache = [row[0] for row in rows if row[0]]
    return _team_stats_cache


def resolve_team_stats_name(team_name, known_teams=None, cutoff=0.78):
    """
    Map a collector name onto an existing team_stats.team value.
    Order: normalize_team exact, stripped-key exact, difflib fuzzy.
    Returns (resolved_name_or_None, method).
    """
    raw = clean_team_name(team_name)
    if not raw:
        return None, "empty"

    known = known_teams if known_teams is not None else load_team_stats_names()
    known_set = set(known)

    normalized = normalize_team(raw)
    if normalized in known_set:
        return normalized, "exact"

    raw_key = match_key(normalized)
    if raw_key:
        for stored in known:
            if match_key(stored) == raw_key:
                return stored, "key"

    candidates = list(known)
    close = difflib.get_close_matches(
        normalized, candidates, n=1, cutoff=cutoff
    )
    if close:
        return close[0], "fuzzy"

    close_key = difflib.get_close_matches(
        raw_key, [match_key(t) for t in known], n=1, cutoff=cutoff
    )
    if close_key:
        hit = close_key[0]
        for stored in known:
            if match_key(stored) == hit:
                return stored, "fuzzy-key"

    return None, "miss"


def save_alias(alias, canonical_name, source="fuzzy"):
    conn = get_db()
    conn.execute(
        """
        INSERT OR REPLACE INTO team_aliases
        (alias, canonical_name, source, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            alias,
            canonical_name,
            source,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    if _alias_cache_loaded and _alias_cache is not None:
        _alias_cache[alias.lower()] = canonical_name


def teams_match(team_a, team_b):
    return normalize_team(team_a) == normalize_team(team_b)


def normalize_fixture(home_team, away_team):
    return normalize_team(home_team), normalize_team(away_team)


if __name__ == "__main__":
    known = load_team_stats_names()
    samples = [
        "1 FC Köln",
        "Arminia Bielefeld",
        "Aalesund",
        "Fredrikstad",
        "Viborg",
        "Auxerre",
        "Sparta Rotterdam",
        "Man Utd",
        "Bayern München",
    ]
    for team in samples:
        resolved, method = resolve_team_stats_name(team, known)
        print(f"{team} -> {resolved} ({method})")
