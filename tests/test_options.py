from datetime import date

from claudeinhood.options.selector import (
    nearest_expiry,
    occ_symbol,
    pick_strike,
    select_contract,
)
from claudeinhood.strategy.base import Side


def test_occ_symbol_format():
    s = occ_symbol("SPY", date(2026, 6, 30), "C", 540.0)
    assert s == "SPY260630C00540000"


def test_nearest_expiry_prefers_0dte():
    today = date(2026, 6, 30)
    expiries = [date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 7)]
    assert nearest_expiry(today, expiries, max_dte=1) == date(2026, 6, 30)


def test_nearest_expiry_none_when_too_far():
    today = date(2026, 6, 30)
    expiries = [date(2026, 7, 10)]
    assert nearest_expiry(today, expiries, max_dte=1) is None


def test_pick_strike_long_is_call_above_spot():
    strike, right = pick_strike(540.0, Side.LONG)
    assert right == "C"
    assert strike >= 540.0


def test_pick_strike_short_is_put_below_spot():
    strike, right = pick_strike(540.0, Side.SHORT)
    assert right == "P"
    assert strike <= 540.0


def test_select_contract_end_to_end():
    today = date(2026, 6, 30)
    choice = select_contract("SPY", 540.0, Side.LONG, today, [today], max_dte=1)
    assert choice is not None
    assert choice.right == "C"
    assert choice.occ_symbol.startswith("SPY260630C")
