"""
2UP Master V3

Approved bookmakers and exchanges.

Only enabled providers will be used
by odds_collector.py and displayed
in Opportunities.
"""

TWO_UP_BOOKMAKERS = {

    "bet365": {
        "display_name": "Bet365",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": True
    },

    "skybet": {
        "display_name": "Sky Bet",
        "provider_type": "bookmaker",
        "enabled": True,
        "two_up": True
    },

    "betfair_exchange": {
        "display_name": "Betfair Exchange",
        "provider_type": "exchange",
        "enabled": True,
        "two_up": False
    }
}


def is_allowed_bookmaker(
    provider_key
):
    provider_key = (
        provider_key
        .strip()
        .lower()
    )

    provider = (
        TWO_UP_BOOKMAKERS.get(
            provider_key
        )
    )

    if not provider:
        return False

    return provider["enabled"]


def get_display_name(
    provider_key
):
    provider_key = (
        provider_key
        .strip()
        .lower()
    )

    provider = (
        TWO_UP_BOOKMAKERS.get(
            provider_key
        )
    )

    if provider:
        return provider[
            "display_name"
        ]

    return provider_key


def get_provider_type(
    provider_key
):
    provider_key = (
        provider_key
        .strip()
        .lower()
    )

    provider = (
        TWO_UP_BOOKMAKERS.get(
            provider_key
        )
    )

    if provider:
        return provider[
            "provider_type"
        ]

    return "unknown"


def is_exchange(
    provider_key
):
    return (
        get_provider_type(
            provider_key
        )
        == "exchange"
    )


def is_two_up_bookmaker(
    provider_key
):
    provider_key = (
        provider_key
        .strip()
        .lower()
    )

    provider = (
        TWO_UP_BOOKMAKERS.get(
            provider_key
        )
    )

    if not provider:
        return False

    return provider[
        "two_up"
    ]


def get_enabled_providers():

    return [

        key

        for key, value
        in TWO_UP_BOOKMAKERS.items()

        if value["enabled"]

    ]


def get_enabled_bookmakers():

    return [

        key

        for key, value
        in TWO_UP_BOOKMAKERS.items()

        if (
            value["enabled"]
            and value["provider_type"]
            == "bookmaker"
        )

    ]


def get_enabled_exchanges():

    return [

        key

        for key, value
        in TWO_UP_BOOKMAKERS.items()

        if (
            value["enabled"]
            and value["provider_type"]
            == "exchange"
        )

    ]


if __name__ == "__main__":

    print(
        "Bookmakers:"
    )

    for provider in (
        get_enabled_bookmakers()
    ):
        print(
            provider
        )

    print(
        "\nExchanges:"
    )

    for provider in (
        get_enabled_exchanges()
    ):
        print(
            provider
        )
