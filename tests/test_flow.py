from datetime import datetime, timedelta, timezone

from claudeinhood.flow.base import FlowReading, NullFlowFilter, flow_allows
from claudeinhood.strategy.base import Side


def test_none_reading_allows():
    ok, why = flow_allows(Side.LONG, None)
    assert ok and "no flow" in why


def test_null_filter_returns_none():
    assert NullFlowFilter().read("SPY") is None


def test_bearish_flow_vetoes_long():
    r = FlowReading(net_sentiment=-0.9, strength=0.9)  # eff ~ -0.81
    ok, why = flow_allows(Side.LONG, r)
    assert not ok and "veto LONG" in why


def test_bullish_flow_vetoes_short():
    r = FlowReading(net_sentiment=0.8, strength=0.8)  # eff ~ 0.64
    ok, _ = flow_allows(Side.SHORT, r)
    assert not ok


def test_flow_aligned_with_trade_allows():
    # Bullish flow + LONG fade = same direction, not opposing -> allow.
    r = FlowReading(net_sentiment=0.9, strength=0.9)
    ok, _ = flow_allows(Side.LONG, r)
    assert ok


def test_weak_flow_does_not_veto():
    r = FlowReading(net_sentiment=-1.0, strength=0.2)  # eff = -0.2 < threshold 0.4
    ok, _ = flow_allows(Side.LONG, r)
    assert ok


def test_stale_flow_fails_open():
    old = datetime.now(timezone.utc) - timedelta(seconds=1200)
    r = FlowReading(net_sentiment=-0.9, strength=0.9, as_of=old)
    ok, why = flow_allows(Side.LONG, r, max_age_seconds=600)
    assert ok and "stale" in why


def test_fresh_flow_still_vetoes():
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(seconds=60)
    r = FlowReading(net_sentiment=-0.9, strength=0.9, as_of=recent)
    ok, _ = flow_allows(Side.LONG, r, max_age_seconds=600, now=now)
    assert not ok
