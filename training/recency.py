"""
Age decay for training labels (Dixon–Coles style).

Original Dixon–Coles (1997) use continuous exponential decay on match
likelihood contributions. We approximate the same idea for XGB rows:

    weight = 0.5 ** (years_ago / half_life_years)

With SAMPLE_WEIGHT_HALF_LIFE_YEARS = 1.5:
  this season ~ 1.0
  ~1.5 years ago ~ 0.50
  ~3 years ago ~ 0.25
  ~6 years ago ~ 0.06 (floored)

Missing dates keep weight 1.0 so live rows without kickoff are not
accidentally down-weighted.
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
        "%d/%m/%Y",
        "%d-%m-%Y",
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
    """Return XGBoost sample_weight for a labelled match."""
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
