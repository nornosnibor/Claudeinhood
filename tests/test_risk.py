from datetime import date

from claudeinhood.risk.manager import RiskConfig, RiskManager, RiskState


def _mgr(equity=500.0, settled=500.0, max_daily=0.25):
    cfg = RiskConfig(max_daily_loss_pct=max_daily, max_risk_per_trade_pct=0.10,
                     max_position_pct=0.50)
    state = RiskState(start_of_day_equity=equity, equity=equity,
                      day=date(2026, 6, 30), settled_cash=settled)
    return RiskManager(cfg, state)


def test_can_trade_initially():
    m = _mgr()
    ok, _ = m.can_trade()
    assert ok


def test_daily_loss_halts_trading():
    m = _mgr(equity=500.0, max_daily=0.25)  # limit = $125
    m.record_fill(-130.0)
    ok, why = m.can_trade()
    assert not ok
    assert "daily loss limit" in why


def test_halt_is_sticky_until_new_day():
    m = _mgr(max_daily=0.25)
    m.record_fill(-130.0)
    assert not m.can_trade()[0]
    # New day resets.
    m.roll_day(date(2026, 7, 1), equity=370.0, settled_cash=370.0)
    assert m.can_trade()[0]


def test_size_respects_settled_cash():
    m = _mgr(equity=500.0, settled=120.0)
    # $1.00 premium -> $100/contract. Only $120 settled -> at most 1 contract.
    qty = m.size_option_order(
        premium_per_contract=1.00, underlying_entry=540.0, underlying_stop=539.0,
    )
    assert qty == 1


def test_size_zero_when_too_expensive():
    m = _mgr(equity=500.0, settled=500.0)
    # $6.00 premium -> $600/contract > max_position (50% of 500 = $250).
    qty = m.size_option_order(
        premium_per_contract=6.00, underlying_entry=540.0, underlying_stop=539.0,
    )
    assert qty == 0


def test_risk_budget_limits_size():
    # Wide stop -> high per-contract risk -> risk budget caps contracts.
    m = _mgr(equity=500.0, settled=500.0)
    qty = m.size_option_order(
        premium_per_contract=0.50, underlying_entry=540.0, underlying_stop=530.0,
        contract_delta=0.5,
    )
    # risk budget = $50; risk/contract = 10 * 0.5 * 100 = $500 -> 0 contracts.
    assert qty == 0
