"""
Team name normalisation.

No fuzzy matching. Every variation is an explicit alias.
Lookup order:
  1. team_aliases table
  2. TEAM_ALIASES in this file
  3. original cleaned string

resolve_team_stats_name also allows a unique stripped-key
equality against team_stats (AJ Auxerre == Auxerre) but
never a similarity score.
"""

import unicodedata
from datetime import datetime, timezone

from database import get_db


def _merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


def _variants(canonical, *aliases):
    """Map every alias (and the canonical itself) to canonical."""
    mapping = {canonical.lower(): canonical}
    for alias in aliases:
        mapping[alias.lower()] = canonical
    return mapping


ENGLAND_PL = _merge(
    _variants("Arsenal", "arsenal fc", "the gunners"),
    _variants("Aston Villa", "villa", "aston villa fc"),
    _variants("Bournemouth", "afc bournemouth", "afc b'mouth", "afr bournemouth"),
    _variants("Brentford", "brentford fc"),
    _variants("Brighton and Hove Albion", "brighton", "brighton & hove albion", "brighton hove albion", "brighton and hove", "bhafc"),
    _variants("Burnley", "burnley fc"),
    _variants("Chelsea", "chelsea fc"),
    _variants("Crystal Palace", "palace", "crystal palace fc", "cpfc"),
    _variants("Everton", "everton fc"),
    _variants("Fulham", "fulham fc"),
    _variants("Ipswich Town", "ipswich", "ipswich town fc"),
    _variants("Leeds United", "leeds", "leeds utd", "leeds united fc"),
    _variants("Leicester City", "leicester", "leicester city fc"),
    _variants("Liverpool", "liverpool fc", "lfc"),
    _variants("Manchester City", "man city", "man city fc", "manchester city fc", "mcfc"),
    _variants("Manchester United", "man utd", "man united", "manchester utd", "manchester utd.", "manchester united fc", "mufc"),
    _variants("Newcastle United", "newcastle", "newcastle utd", "newcastle united fc", "nufc"),
    _variants("Nottingham Forest", "nottm forest", "notts forest", "forest", "nottingham forest fc", "nffc"),
    _variants("Southampton", "southampton fc", "saints"),
    _variants("Sunderland", "sunderland afc", "sunderland a.f.c."),
    _variants("Tottenham", "spurs", "tottenham hotspur", "tottenham hotspur fc", "tottenham hotspurs", "thfc"),
    _variants("West Ham United", "west ham", "west ham utd", "west ham united fc", "whu"),
    _variants("Wolverhampton Wanderers", "wolves", "wolverhampton", "wolverhampton wanderers fc", "wwfc"),
    _variants("Luton Town", "luton", "luton town fc"),
    _variants("Sheffield United", "sheff utd", "sheffield utd", "sheffield united fc"),
    _variants("West Bromwich Albion", "west brom", "west bromwich", "wba", "west bromwich albion fc"),
)

ENGLAND_CHAMPIONSHIP = _merge(
    _variants("Birmingham City", "birmingham", "birmingham city fc"),
    _variants("Blackburn Rovers", "blackburn", "blackburn rovers fc"),
    _variants("Bristol City", "bristol city fc"),
    _variants("Cardiff City", "cardiff", "cardiff city fc"),
    _variants("Charlton Athletic", "charlton", "charlton athletic fc"),
    _variants("Coventry City", "coventry", "coventry city fc"),
    _variants("Derby County", "derby", "derby county fc"),
    _variants("Hull City", "hull", "hull city afc", "hull city fc"),
    _variants("Middlesbrough", "boro", "middlesbrough fc"),
    _variants("Millwall", "millwall fc"),
    _variants("Norwich City", "norwich", "norwich city fc"),
    _variants("Oxford United", "oxford", "oxford utd", "oxford united fc"),
    _variants("Portsmouth", "portsmouth fc", "pompey"),
    _variants("Preston North End", "preston", "preston ne", "pne", "preston north end fc"),
    _variants("Queens Park Rangers", "qpr", "queens park rangers fc"),
    _variants("Sheffield Wednesday", "sheff wed", "sheffield wed", "sheffield wednesday fc"),
    _variants("Stoke City", "stoke", "stoke city fc"),
    _variants("Swansea City", "swansea", "swansea city afc", "swansea city fc"),
    _variants("Watford", "watford fc"),
    _variants("Wrexham", "wrexham afc", "wrexham fc"),
)

ENGLAND_L1_L2 = _merge(
    _variants("Barnsley", "barnsley fc"),
    _variants("Bolton Wanderers", "bolton", "bolton wanderers fc"),
    _variants("Bradford City", "bradford", "bradford city afc"),
    _variants("Burton Albion", "burton", "burton albion fc"),
    _variants("Cambridge United", "cambridge", "cambridge utd"),
    _variants("Exeter City", "exeter", "exeter city fc"),
    _variants("Huddersfield Town", "huddersfield", "huddersfield town afc"),
    _variants("Leyton Orient", "orient", "leyton orient fc"),
    _variants("Lincoln City", "lincoln", "lincoln city fc"),
    _variants("Mansfield Town", "mansfield", "mansfield town fc"),
    _variants("Northampton Town", "northampton", "northampton town fc"),
    _variants("Peterborough United", "peterborough", "peterborough utd", "posh"),
    _variants("Plymouth Argyle", "plymouth", "plymouth argyle fc"),
    _variants("Reading", "reading fc"),
    _variants("Rotherham United", "rotherham", "rotherham utd"),
    _variants("Stevenage", "stevenage fc"),
    _variants("Stockport County", "stockport", "stockport county fc"),
    _variants("Wigan Athletic", "wigan", "wigan athletic fc"),
    _variants("Wycombe Wanderers", "wycombe", "wycombe wanderers fc"),
    _variants("Blackpool", "blackpool fc"),
    _variants("Doncaster Rovers", "doncaster", "doncaster rovers fc"),
)

SCOTLAND = _merge(
    _variants("Aberdeen", "aberdeen fc"),
    _variants("Celtic", "celtic fc", "glasgow celtic"),
    _variants("Dundee", "dundee fc"),
    _variants("Dundee United", "dundee utd", "dundee united fc"),
    _variants("Falkirk", "falkirk fc"),
    _variants("Heart Of Midlothian", "hearts", "heart of midlothian", "hearts fc", "heart of midlothian fc"),
    _variants("Hibernian", "hibs", "hibernian fc", "hibernian edinburgh"),
    _variants("Kilmarnock", "killie", "kilmarnock fc"),
    _variants("Livingston", "livingston fc", "livi"),
    _variants("Motherwell", "motherwell fc"),
    _variants("Rangers", "rangers fc", "glasgow rangers", "the rangers"),
    _variants("Ross County", "ross county fc"),
    _variants("St Johnstone", "st johnstone fc", "saint johnstone"),
    _variants("St Mirren", "st mirren fc", "saint mirren"),
)

GERMANY = _merge(
    _variants("Bayern Munich", "bayern", "fc bayern", "fc bayern munich", "fc bayern munchen", "fc bayern münchen", "bayern munchen", "bayern münchen", "bayern muenchen"),
    _variants("Borussia Dortmund", "dortmund", "bvb", "borussia dortmund 09"),
    _variants("Bayer Leverkusen", "leverkusen", "bayer 04", "bayer 04 leverkusen", "bayer leverkusen"),
    _variants("RB Leipzig", "leipzig", "rbl", "rasenballsport leipzig"),
    _variants("Eintracht Frankfurt", "frankfurt", "sge", "eintracht frankfurt fc"),
    _variants("Borussia Monchengladbach", "gladbach", "mgladbach", "m'gladbach", "borussia moenchengladbach", "borussia mönchengladbach", "borussia m gladbach", "bmgl"),
    _variants("VfB Stuttgart", "stuttgart", "vfb stuttgart"),
    _variants("VfL Wolfsburg", "wolfsburg", "vfl wolfsburg"),
    _variants("SC Freiburg", "freiburg", "sport club freiburg"),
    _variants("TSG Hoffenheim", "hoffenheim", "1899 hoffenheim", "tsg 1899 hoffenheim"),
    _variants("FC Augsburg", "augsburg", "fc augsburg 1907"),
    _variants("1. FSV Mainz 05", "mainz", "mainz 05", "fsv mainz 05", "1 fsv mainz 05"),
    _variants("1. FC Union Berlin", "union berlin", "union", "1 fc union berlin", "fc union berlin"),
    _variants("Werder Bremen", "bremen", "sv werder bremen"),
    _variants("FC Heidenheim", "heidenheim", "1 fc heidenheim", "1. fc heidenheim"),
    _variants("FC St. Pauli", "st pauli", "fc st pauli", "st. pauli", "fc st. pauli", "sankt pauli"),
    _variants("Holstein Kiel", "kiel", "kieler sv holstein"),
    _variants("VfL Bochum", "bochum", "vfl bochum 1848"),
    _variants("FC Koln", "koln", "köln", "cologne", "1 fc koln", "1 fc köln", "1. fc koln", "1. fc köln", "1. fc cologne", "fc köln", "fc cologne"),
    _variants("Arminia Bielefeld", "bielefeld", "dsc arminia bielefeld", "arminia", "dsc arminia"),
    _variants("Hamburger SV", "hamburg", "hsv", "hamburger sv"),
    _variants("Hertha BSC", "hertha", "hertha berlin", "hertha bsc berlin"),
    _variants("Schalke 04", "schalke", "fc schalke 04"),
    _variants("Fortuna Dusseldorf", "dusseldorf", "fortuna düsseldorf", "fortuna duesseldorf"),
    _variants("Hannover 96", "hannover", "hannover 96"),
    _variants("1. FC Nurnberg", "nurnberg", "nürnberg", "1 fc nurnberg", "1. fc nürnberg", "nuremberg"),
    _variants("Darmstadt 98", "darmstadt", "sv darmstadt 98"),
    _variants("Karlsruher SC", "karlsruhe", "ksc"),
    _variants("Greuther Furth", "furth", "greuther fürth", "spvgg greuther furth"),
    _variants("Paderborn", "sc paderborn", "sc paderborn 07"),
    _variants("Elversberg", "sv elversberg"),
    _variants("Magdeburg", "1 fc magdeburg", "1. fc magdeburg"),
)

SPAIN = _merge(
    _variants("Real Madrid", "real madrid cf", "real madrid c.f."),
    _variants("Barcelona", "fc barcelona", "barca", "barça", "barcelona fc"),
    _variants("Atletico Madrid", "atletico", "atlético madrid", "atletico de madrid", "club atletico de madrid", "atm"),
    _variants("Athletic Club", "athletic bilbao", "athletic", "athletic club bilbao"),
    _variants("Real Sociedad", "sociedad", "real sociedad de futbol"),
    _variants("Real Betis", "betis", "real betis balompie"),
    _variants("Villarreal", "villarreal cf", "villarreal cf"),
    _variants("Sevilla", "sevilla fc"),
    _variants("Valencia", "valencia cf"),
    _variants("Celta Vigo", "celta", "rc celta", "celta de vigo"),
    _variants("Rayo Vallecano", "rayo", "rayo vallecano de madrid"),
    _variants("Osasuna", "ca osasuna"),
    _variants("Getafe", "getafe cf"),
    _variants("Mallorca", "rcd mallorca"),
    _variants("Girona", "girona fc"),
    _variants("Las Palmas", "ud las palmas"),
    _variants("Alaves", "alavés", "deportivo alaves", "deportivo alavés"),
    _variants("Espanyol", "rcd espanyol", "espanol"),
    _variants("Leganes", "leganés", "cd leganes"),
    _variants("Valladolid", "real valladolid"),
    _variants("Cadiz", "cádiz", "cadiz cf"),
    _variants("Granada", "granada cf"),
)

ITALY = _merge(
    _variants("Inter Milan", "inter", "internazionale", "fc internazionale", "fc internazionale milano", "inter milano"),
    _variants("AC Milan", "milan", "ac milan", "a.c. milan"),
    _variants("Juventus", "juve", "juventus fc"),
    _variants("Napoli", "ssc napoli", "ss napoli"),
    _variants("AS Roma", "roma", "as roma"),
    _variants("Lazio", "ss lazio"),
    _variants("Atalanta", "atalanta bc", "atalanta bergamo"),
    _variants("Fiorentina", "acf fiorentina"),
    _variants("Bologna", "bologna fc", "bologna 1909"),
    _variants("Torino", "torino fc"),
    _variants("Udinese", "udinese calcio"),
    _variants("Genoa", "genoa cfc"),
    _variants("Cagliari", "cagliari calcio"),
    _variants("Lecce", "us lecce"),
    _variants("Empoli", "empoli fc"),
    _variants("Monza", "ac monza", "ss monza"),
    _variants("Parma", "parma calcio", "parma calcio 1913"),
    _variants("Como", "como 1907", "calcio como"),
    _variants("Venezia", "venezia fc"),
    _variants("Hellas Verona", "verona", "hellas verona fc"),
    _variants("Sassuolo", "us sassuolo"),
    _variants("Salernitana", "us salernitana"),
)

FRANCE = _merge(
    _variants("Paris Saint Germain", "psg", "paris sg", "paris saint-germain", "paris saint germain fc"),
    _variants("Marseille", "olympique marseille", "olympique de marseille", "om"),
    _variants("Lyon", "olympique lyon", "olympique lyonnais", "ol"),
    _variants("Monaco", "as monaco", "as monaco fc"),
    _variants("Lille", "losc", "lille osc", "losc lille"),
    _variants("Nice", "ogc nice"),
    _variants("Rennes", "stade rennais", "stade rennais fc"),
    _variants("Lens", "rc lens"),
    _variants("Strasbourg", "rc strasbourg", "racing strasbourg"),
    _variants("Nantes", "fc nantes"),
    _variants("Reims", "stade de reims"),
    _variants("Toulouse", "toulouse fc"),
    _variants("Brest", "stade brestois", "stade brestois 29"),
    _variants("Montpellier", "montpellier hsc"),
    _variants("Le Havre", "le havre ac", "hac"),
    _variants("Angers", "angers sco"),
    _variants("AJ Auxerre", "auxerre", "aj auxerre", "auxerre fc"),
    _variants("Saint-Etienne", "saint etienne", "as saint etienne", "asse", "st etienne"),
    _variants("Metz", "fc metz"),
)

NETHERLANDS = _merge(
    _variants("Ajax", "afc ajax", "ajax amsterdam"),
    _variants("PSV Eindhoven", "psv", "psv eindhoven"),
    _variants("Feyenoord", "feyenoord rotterdam"),
    _variants("AZ Alkmaar", "az", "az alkmaar"),
    _variants("FC Twente", "twente", "fc twente enschede"),
    _variants("FC Utrecht", "utrecht"),
    _variants("Sparta Rotterdam", "sparta rotterdam", "sparta r'dam", "sparta rdam"),
    _variants("PEC Zwolle", "zwolle", "pec zwolle", "fc zwolle"),
    _variants("NEC Nijmegen", "nec", "nec nijmegen"),
    _variants("Go Ahead Eagles", "go ahead", "ga eagles"),
    _variants("SC Heerenveen", "heerenveen"),
    _variants("FC Groningen", "groningen"),
    _variants("Heracles", "heracles almelo"),
    _variants("Fortuna Sittard", "sittard"),
    _variants("NAC Breda", "nac", "nac breda"),
    _variants("Willem II", "willem ii tilburg"),
    _variants("RKC Waalwijk", "rkc", "waalwijk"),
    _variants("Almere City", "almere"),
)

BELGIUM = _merge(
    _variants("Club Brugge", "club brugge kv", "club bruges", "club brugge kv"),
    _variants("Anderlecht", "rsc anderlecht", "r.s.c. anderlecht"),
    _variants("Union Saint-Gilloise", "union sg", "royer union saint gilloise", "union saint gilloise", "rusg"),
    _variants("Genk", "krc genk", "racing genk"),
    _variants("Gent", "kaa gent", "kaa la gantoise", "la gantoise"),
    _variants("Royal Antwerp", "antwerp", "royal antwerp fc", "antwerp fc"),
    _variants("Standard Liege", "standard", "standard liège", "standard de liege"),
    _variants("Mechelen", "kv mechelen", "yellow red kv mechelen"),
    _variants("Cercle Brugge", "cercle", "cercle brugge ksv"),
    _variants("Charleroi", "sporting charleroi", "royal charleroi"),
    _variants("Westerlo", "kvc westerlo"),
    _variants("OH Leuven", "leuven", "oud-heverlee leuven"),
    _variants("Kortrijk", "kv kortrijk"),
    _variants("Sint-Truiden", "sint truiden", "stvv", "sint-truidense"),
)

PORTUGAL = _merge(
    _variants("Sporting CP", "sporting", "sporting lisbon", "sporting clube de portugal", "sporting portugal"),
    _variants("FC Porto", "porto", "futebol clube do porto"),
    _variants("Benfica", "sl benfica", "sport lisboa e benfica"),
    _variants("SC Braga", "braga", "sporting braga", "sporting clube de braga"),
    _variants("Vitoria Guimaraes", "guimaraes", "vitoria sc", "vitória guimarães"),
    _variants("Boavista", "boavista fc"),
    _variants("Famalicao", "famalicão", "fc famalicao"),
    _variants("Moreirense", "moreirense fc"),
    _variants("Rio Ave", "rio ave fc"),
    _variants("Estoril", "estoril praia", "gd estoril praia"),
    _variants("Casa Pia", "casa pia ac"),
    _variants("Arouca", "fc arouca"),
    _variants("Gil Vicente", "gil vicente fc"),
    _variants("Nacional", "cd nacional"),
    _variants("Santa Clara", "cd santa clara"),
)

DENMARK = _merge(
    _variants("FC Copenhagen", "copenhagen", "fc kobenhavn", "fc københavn", "kobenhavn", "københavn", "fck"),
    _variants("Brondby", "brøndby", "brondby if", "brøndby if"),
    _variants("FC Midtjylland", "midtjylland", "fc midtjylland"),
    _variants("Aarhus", "agf", "agf aarhus", "aarhus gf"),
    _variants("Nordsjaelland", "fc nordsjaelland", "nordsjælland", "fc nordsjælland"),
    _variants("Randers", "randers fc"),
    _variants("Viborg", "viborg ff", "viborg f.f."),
    _variants("Lyngby", "lyngby bk", "lyngby boldklub"),
    _variants("Silkeborg", "silkeborg if"),
    _variants("Sonderjyske", "sønderjyske", "sonderjysk e"),
    _variants("Vejle", "vejle bk", "vejle boldklub"),
    _variants("AaB", "aalborg", "aalborg bk", "aab aalborg"),
)

NORWAY = _merge(
    _variants("Bodo/Glimt", "bodo glimt", "bodø/glimt", "bodoe/glimt", "fk bodo glimt", "fk bodø/glimt"),
    _variants("Molde", "molde fk"),
    _variants("Rosenborg", "rosenborg bk", "rbk"),
    _variants("Viking", "viking fk", "viking stavanger"),
    _variants("Brann", "sk brann", "brann bergen"),
    _variants("Fredrikstad", "fredrikstad fk", "ffk"),
    _variants("Aalesund", "aalesunds fk", "aalesund fk", "alesund"),
    _variants("IK Start", "start", "ik start", "start kristiansand"),
    _variants("Tromso", "tromsø", "tromso il", "til"),
    _variants("Lillestrom", "lillestrøm", "lillestrom sk"),
    _variants("Sarpsborg 08", "sarpsborg", "sarpsborg 08 ff"),
    _variants("Stromsgodset", "strømsgodset", "stromsgodset if"),
    _variants("Haugesund", "fk haugesund"),
    _variants("Kristiansund", "kristiansund bk"),
    _variants("HamKam", "hamkam", "hamar kammeratene"),
    _variants("Odd", "odds bk", "odd grenland"),
)

SWEDEN = _merge(
    _variants("Malmo FF", "malmo", "malmö", "malmo ff", "malmö ff", "mff"),
    _variants("AIK", "aik stockholm", "aik fotboll"),
    _variants("Djurgardens IF", "djurgardens", "djurgårdens", "djurgarden", "djurgården", "dif"),
    _variants("Hammarby", "hammarby if", "bajen"),
    _variants("IFK Goteborg", "ifk göteborg", "goteborg", "göteborg"),
    _variants("IFK Norrkoping", "norrkoping", "norrköping", "ifk norrköping"),
    _variants("Elfsborg", "if elfsborg"),
    _variants("Hacken", "bk hacken", "bk häcken"),
    _variants("Sirius", "ik sirius"),
    _variants("Mjallby", "mjällby", "mjallby aif"),
    _variants("Kalmar FF", "kalmar"),
    _variants("Varnamo", "ifk varnamo", "värnamo"),
    _variants("Brommapojkarna", "if brommapojkarna", "bp"),
    _variants("GAIS", "gais goteborg"),
)

IRELAND = _merge(
    _variants("Shamrock Rovers", "shamrock", "shamrock rovers fc"),
    _variants("Shelbourne", "shelbourne fc"),
    _variants("Derry City", "derry", "derry city fc"),
    _variants("St Patricks Athletic", "st pats", "st patrick's athletic", "saint patricks"),
    _variants("Bohemians", "bohemian fc", "boh's"),
    _variants("Sligo Rovers", "sligo"),
    _variants("Dundalk", "dundalk fc"),
    _variants("Waterford", "waterford fc"),
    _variants("Galway United", "galway", "galway utd"),
    _variants("Cork City", "cork", "cork city fc"),
)

MLS = _merge(
    _variants("Inter Miami CF", "inter miami", "club internacional de futbol miami"),
    _variants("Los Angeles FC", "lafc", "la fc"),
    _variants("LA Galaxy", "galaxy", "los angeles galaxy"),
    _variants("Atlanta United", "atlanta", "atlanta utd", "atlanta united fc"),
    _variants("New York City FC", "nycfc", "new york city", "nycf c"),
    _variants("New York Red Bulls", "ny red bulls", "red bulls", "new york red bull"),
    _variants("Seattle Sounders", "sounders", "seattle sounders fc"),
    _variants("Portland Timbers", "timbers", "portland"),
    _variants("Sporting Kansas City", "sporting kc", "sporting kansas", "skc"),
    _variants("St Louis City SC", "st louis city", "st. louis city", "st louis city sc"),
    _variants("Austin FC", "austin"),
    _variants("Nashville SC", "nashville"),
    _variants("FC Cincinnati", "cincinnati"),
    _variants("Columbus Crew", "columbus", "the crew"),
    _variants("Chicago Fire", "chicago fire fc"),
    _variants("New England Revolution", "new england", "revs"),
    _variants("Philadelphia Union", "philadelphia", "the union"),
    _variants("Orlando City", "orlando city sc", "orlando"),
    _variants("Charlotte FC", "charlotte"),
    _variants("DC United", "d.c. united", "dc utd"),
    _variants("Toronto FC", "toronto"),
    _variants("CF Montreal", "montreal", "cf montréal", "impact"),
    _variants("Vancouver Whitecaps", "whitecaps", "vancouver"),
    _variants("Real Salt Lake", "salt lake", "rsl"),
    _variants("Colorado Rapids", "colorado", "rapids"),
    _variants("FC Dallas", "dallas"),
    _variants("Houston Dynamo", "houston", "dynamo"),
    _variants("Minnesota United", "minnesota", "loons"),
    _variants("San Jose Earthquakes", "san jose", "earthquakes", "quakes"),
    _variants("San Diego FC", "san diego"),
)

TEAM_ALIASES = _merge(
    ENGLAND_PL,
    ENGLAND_CHAMPIONSHIP,
    ENGLAND_L1_L2,
    SCOTLAND,
    GERMANY,
    SPAIN,
    ITALY,
    FRANCE,
    NETHERLANDS,
    BELGIUM,
    PORTUGAL,
    DENMARK,
    NORWAY,
    SWEDEN,
    IRELAND,
    MLS,
)

_PREFIXES = (
    "1 fc ", "1 ", "fc ", "afc ", "sc ", "sv ", "as ", "ac ",
    "fk ", "if ", "bk ", "sk ", "rc ", "rsc ", "krc ", "kaa ",
    "sl ", "cf ", "cd ", "ud ", "ss ", "us ", "tsg ", "ik ",
    "pec ", "aj ", "ogc ", "rcd ", "ud ",
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
            if alias:
                cache[alias.lower()] = canonical_name
    except Exception:
        pass
    _alias_cache = cache
    _alias_cache_loaded = True


def reload_alias_cache():
    global _team_stats_cache
    _team_stats_cache = None
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
    return " ".join(team_name.split())


def _lookup_alias(cleaned):
    if not cleaned:
        return None
    lower = cleaned.lower()
    folded = _strip_accents(lower)

    if not _alias_cache_loaded:
        _load_alias_cache()

    for key in (lower, folded):
        hit = _alias_cache.get(key)
        if hit:
            return hit
        hit = TEAM_ALIASES.get(key)
        if hit:
            return hit
    return None


def normalize_team(team_name):
    cleaned = clean_team_name(team_name)
    if not cleaned:
        return ""
    mapped = _lookup_alias(cleaned)
    if mapped:
        return mapped
    return cleaned


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


def resolve_team_stats_name(team_name, known_teams=None, cutoff=None):
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
        hits = [stored for stored in known if match_key(stored) == raw_key]
        if len(hits) == 1:
            return hits[0], "key"

    return None, "miss"


def save_alias(alias, canonical_name, source="manual"):
    conn = get_db()
    try:
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
    except Exception:
        conn.execute(
            """
            INSERT OR REPLACE INTO team_aliases
            (alias, canonical_name)
            VALUES (?, ?)
            """,
            (alias, canonical_name),
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
    samples = [
        "1 FC Köln",
        "FC St Pauli",
        "Arminia Bielefeld",
        "Aalesund",
        "Fredrikstad",
        "Viborg",
        "Lyngby",
        "Auxerre",
        "Sparta Rotterdam",
        "PEC Zwolle",
        "Bodo/Glimt",
        "Start",
        "Man Utd",
        "Wolves",
        "Bayern München",
        "PSG",
    ]
    print(f"{len(TEAM_ALIASES)} explicit aliases loaded")
    for team in samples:
        print(f"{team} -> {normalize_team(team)}")
