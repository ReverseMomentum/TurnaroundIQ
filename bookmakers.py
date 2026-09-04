"""
Approved back books for opportunities.

Lay prices are estimated when no exchange feed is present.
"""

TWO_UP_BOOKMAKERS = {
    "bet365": {
        "display_name": "Bet365",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": True,
    },
    "pinnacle": {
        "display_name": "Pinnacle",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": False,
    },
    "paddypower": {
        "display_name": "Paddy Power",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": True,
    },
    "betfair_sb": {
        "display_name": "Betfair Sportsbook",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": True,
    },
    "kambi": {
        "display_name": "Kambi",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": False,
    },
    "skybet": {
        "display_name": "Sky Bet",
        "provider_type": "bookmaker",
        "enabled": False,
        "two_up": True,
    },
    "betfair_exchange": {
        "display_name": "Betfair Exchange",
        "provider_type": "exchange",
        "enabled": False,
        "two_up": False,
    },
}


def is_allowed_bookmaker(provider_key):
    provider = TWO_UP_BOOKMAKERS.get(provider_key.strip().lower())
    return bool(provider and provider["enabled"])


def get_display_name(provider_key):
    provider = TWO_UP_BOOKMAKERS.get(provider_key.strip().lower())
    if provider:
        return provider["display_name"]
    return provider_key


def get_provider_type(provider_key):
    provider = TWO_UP_BOOKMAKERS.get(provider_key.strip().lower())
    if provider:
        return provider["provider_type"]
    return "unknown"


def is_exchange(provider_key):
    return get_provider_type(provider_key) == "exchange"


def is_two_up_bookmaker(provider_key):
    provider = TWO_UP_BOOKMAKERS.get(provider_key.strip().lower())
    if not provider:
        return False
    return provider["two_up"]


def get_enabled_providers():
    return [key for key, value in TWO_UP_BOOKMAKERS.items() if value["enabled"]]


def get_enabled_bookmakers():
    return [
        key
        for key, value in TWO_UP_BOOKMAKERS.items()
        if value["enabled"] and value["provider_type"] == "bookmaker"
    ]


def get_enabled_exchanges():
    return [
        key
        for key, value in TWO_UP_BOOKMAKERS.items()
        if value["enabled"] and value["provider_type"] == "exchange"
    ]
