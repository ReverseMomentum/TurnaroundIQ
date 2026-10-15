"""Lay-the-draw test maths (scripts/lay_draw_test.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lay_draw_test as t  # noqa: E402


def test_market_lambdas_reproduce_the_market():
    ph, pd, pa = t.market_fair((2.2, 3.4, 3.4))
    lh, la = t.market_lambdas(ph, pd, pa)
    assert t.draw_prob(lh, la) == pytest.approx(pd, abs=0.01) and lh > la


def test_hold_and_trade_profit_signs():
    assert t.hold_pl(3.5, False, 0.02) == pytest.approx(9.8)
    assert t.hold_pl(3.5, True, 0.02) == pytest.approx(-25)
    lam = (1.4, 1.1)
    early_goal = t.trade_pl(3.5, lam, [(10, 1), (80, 2)], True, 70, 0.0)
    goalless = t.trade_pl(3.5, lam, [], True, 70, 0.0)
    assert early_goal > 0 > goalless                   # a goal lets you green up; 0-0 at 70' costs


def test_winner_test_one_x_two_sums_to_one():
    import winner_test as w
    h, d, a = w.one_x_two(1.6, 1.1)
    assert h + d + a == pytest.approx(1) and h > a and d == pytest.approx(t.draw_prob(1.6, 1.1), abs=1e-6)


def test_two_up_roi_counts_two_up_as_paid():
    import two_up_test as tu
    ss = [{"odds": 3.0, "won": 0, "up2": 1, "paid": 1}, {"odds": 3.0, "won": 0, "up2": 0, "paid": 0}]
    assert tu._roi(ss, "paid") == (pytest.approx(10.0), pytest.approx(0.5))   # +20 - 10 over £20
    assert tu._roi(ss, "won") == (pytest.approx(-20.0), pytest.approx(-1.0))
