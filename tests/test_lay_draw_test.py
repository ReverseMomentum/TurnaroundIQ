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
