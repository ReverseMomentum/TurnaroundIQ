"""
Extra-place engine: each-way terms -> market place probability, edge and EV.

An each-way bet is two equal bets: win, and place at a fraction of the win
odds for finishing in the paid places. With win odds O and fraction f, the
place part pays 1 + (O - 1) * f, so the bookmaker is effectively offering the
place at implied probability 1 / (1 + (O - 1) * f).

Extra-place promotions raise the places paid (e.g. 5 instead of 3) at the same
odds and fraction. The value comes almost entirely from P(4th) + P(5th): the
bookmaker keeps the price, the bettor gets paid on more of the distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Terms:
    bookmaker: str
    places: int              # places paid under this offer (incl. extra places)
    fraction: float          # e.g. 0.2 for 1/5 odds
    standard_places: int     # what the race pays normally


def standard_terms(field_size: int, handicap: bool = False) -> tuple[int, float]:
    """UK standard each-way terms (places, fraction) for a field size."""
    if field_size <= 4:
        return 1, 0.0  # win only
    if field_size <= 7:
        return 2, 0.25
    if handicap and field_size >= 16:
        return 4, 0.25
    if handicap and field_size >= 12:
        return 3, 0.25
    return 3, 0.2


def parse_fraction(v) -> Optional[float]:
    """'1/5', '0.2', 0.2, 5 (meaning 1/5) -> 0.2"""
    if v is None or v == "":
        return None
    if isinstance(v, str) and "/" in v:
        a, b = v.split("/", 1)
        try:
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x >= 1:
        return 1.0 / x
    return x if x > 0 else None


def place_odds(win_odds: float, fraction: float) -> float:
    return 1.0 + (float(win_odds) - 1.0) * float(fraction)


def evaluate(p_win: float, top: list, win_odds: float, terms: Terms) -> dict:
    """
    p_win: model win probability
    top:   cumulative top-k probabilities, top[k-1] = P(finish in top k)
    Returns the market vs model numbers for one runner under one offer.
    EVs are per £1 staked (each-way EV is per £1 total, split 50p / 50p).
    """
    k, k_std = terms.places, terms.standard_places

    def top_k(kk):
        if kk <= 0:
            return 0.0
        return float(top[min(kk, len(top)) - 1])

    po = place_odds(win_odds, terms.fraction)
    model_place = top_k(k)
    market_place = 1.0 / po
    win_ev = p_win * win_odds - 1.0
    place_ev = model_place * po - 1.0
    return {
        "bookmaker": terms.bookmaker,
        "places_paid": k,
        "standard_places": k_std,
        "fraction": terms.fraction,
        "win_odds": float(win_odds),
        "place_odds": po,
        "model_probability": model_place,
        "market_probability": market_place,
        "edge": model_place - market_place,
        "extra_place_probability": model_place - top_k(k_std),
        "standard_place_probability": top_k(k_std),
        "win_ev": win_ev,
        "place_ev": place_ev,
        "each_way_ev": 0.5 * (win_ev + place_ev),
        "market_win_probability": 1.0 / win_odds,
    }


def shrink(ev: dict, w: float) -> dict:
    """
    Pull the model's place probability toward the bookmaker's by factor w
    (1 = trust the model fully, 0 = no edge). Fitted on past races so that
    the EV shown matches what similar picks actually returned; it corrects
    for over-confident estimates and for picking the biggest (most
    over-estimated) edges. The win part is left as it is.
    """
    raw = ev["model_probability"]
    m = ev["market_probability"]
    adj = min(1.0, max(0.0, m + w * (raw - m)))
    place_ev = adj * ev["place_odds"] - 1.0
    return {**ev, "raw_model_probability": raw, "model_probability": adj, "edge": adj - m,
            "place_ev": place_ev, "each_way_ev": 0.5 * (ev["win_ev"] + place_ev), "edge_shrink": w}


MIN_VALUE_EV = 0.04   # the grade-B line: smaller edges did not hold up in the backtest


def min_value_odds(p_win: float, p_place: float, fraction: float, edge_shrink=None,
                   min_ev: float = MIN_VALUE_EV) -> Optional[float]:
    """
    Lowest decimal win odds at which an each-way bet on these terms has EV >=
    min_ev, using the model's win and place chances (place chance shrunk
    toward the bookmaker's as in shrink()). EV rises with the odds, so this is
    a bisection. None if no price up to 1000 gets there.
    """
    if not fraction or p_place <= 0:
        return None

    def ev(o):
        po = 1.0 + (o - 1.0) * fraction
        p = p_place
        if edge_shrink is not None:
            m = 1.0 / po
            p = min(1.0, max(0.0, m + float(edge_shrink) * (p_place - m)))
        return 0.5 * (p_win * o - 1.0) + 0.5 * (p * po - 1.0)

    lo, hi = 1.01, 1000.0
    if ev(hi) < min_ev:
        return None
    if ev(lo) >= min_ev:
        return lo
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if ev(mid) >= min_ev:
            hi = mid
        else:
            lo = mid
    return round(hi, 2)


# Win-odds brackets (decimal) shared by the backtest, calibration report and Tracker:
# evens-2/1, 2/1-4/1, 4/1-7/1, 7/1-11/1, 11/1-15/1, 15/1-20/1, 20/1-33/1, 33/1-50/1, 50/1+
ODDS_BANDS = ((1.0, 3.0), (3.0, 5.0), (5.0, 8.0), (8.0, 12.0), (12.0, 16.0), (16.0, 21.0),
              (21.0, 34.0), (34.0, 51.0), (51.0, 1e9))


def band_label(lo: float, hi: float) -> str:
    return f"{lo:g}+" if hi >= 1e9 else f"{lo:g}-{hi:g}"


def odds_band(odds: float) -> str:
    for lo, hi in ODDS_BANDS:
        if odds < hi:
            return band_label(lo, hi)
    return band_label(*ODDS_BANDS[-1])
