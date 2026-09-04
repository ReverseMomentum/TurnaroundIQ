"""
Age decay for training labels.

weight = 0.5 ** (years_ago / half_life_years)

This season ~ 1.0
2 years ago ~ 0.50
4 years ago ~ 0.25
8 years ago ~ 0.06
"""

from datetime import datetime, timezone

from constants import (
    SAMPLE_WEIGHT_HALF_LIFE_YEARS,
    SAMPLE_WEIGHT_FLOOR,
)


def parse_match_date(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[:19], fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def sample_weight_from_date(
    match_date,
    as_of=None,
    half_life_years=SAMPLE_WEIGHT_HALF_LIFE_YEARS,
    floor=SAMPLE_WEIGHT_FLOOR,
):
    """
    Return XGBoost sample_weight for a labelled match.
    Missing / unparsable dates keep weight 1.0 so a live
    API result without a kickoff date is not down-weighted.
    """
    parsed = parse_match_date(match_date) if not isinstance(
        match_date, datetime
    ) else match_date

    if parsed is None:
        return 1.0

    if as_of is None:
        as_of = datetime.now(timezone.utc)
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    years_ago = (as_of - parsed).total_seconds() / (365.25 * 24 * 3600)

    if years_ago <= 0:
        return 1.0

    if half_life_years <= 0:
        return 1.0

    weight = 0.5 ** (years_ago / half_life_years)
    return round(max(weight, floor), 4)
