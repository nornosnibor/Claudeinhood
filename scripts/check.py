#!/usr/bin/env python3
"""Connectivity + signal smoke test against your Alpaca paper account.

Verifies auth, prints the account, pulls recent SPY bars, and shows the current
indicator snapshot + what the strategy would do right now. Places NO orders.

    python scripts/check.py
"""
from __future__ import annotations

import os
import sys

# Make the package importable when run as `python scripts/check.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from claudeinhood.config import load_config
from claudeinhood.data.alpaca_data import AlpacaData
from claudeinhood.data.indicators import compute_snapshot
from claudeinhood.strategy.vwap_reversion import VwapReversionStrategy


def main() -> int:
    cfg = load_config()
    problems = cfg.validate_for_live()
    if problems:
        print("Config problem:", "; ".join(problems))
        return 1

    # --- Auth + account ---
    from alpaca.trading.client import TradingClient

    tc = TradingClient(cfg.alpaca_api_key, cfg.alpaca_secret_key, paper=cfg.alpaca_paper)
    acct = tc.get_account()
    print("=== ALPACA PAPER ACCOUNT ===")
    print(f"  status        : {acct.status}")
    print(f"  equity        : ${float(acct.equity):,.2f}")
    print(f"  cash          : ${float(acct.cash):,.2f}")
    print(f"  buying_power  : ${float(acct.buying_power):,.2f}")
    print(f"  options_level : {getattr(acct, 'options_trading_level', 'n/a')}")

    clock = tc.get_clock()
    print(f"  market_open   : {clock.is_open}  (next open {clock.next_open})")

    # --- Data + signal ---
    data = AlpacaData(cfg.alpaca_api_key, cfg.alpaca_secret_key, feed=cfg.alpaca_data_feed)
    df_all = data.recent_minute_bars(cfg.primary_symbol)
    if df_all.empty:
        print(f"\nNo recent {cfg.primary_symbol} bars returned (feed={cfg.alpaca_data_feed}).")
        return 0
    df = AlpacaData.current_session_only(df_all)
    print(f"\n=== {cfg.primary_symbol} DATA ({len(df)} bars this session, feed={cfg.alpaca_data_feed}) ===")
    last = df.iloc[-1]
    print(f"  last bar @ {df.index[-1]}  close={last['close']:.2f}  vol={int(last['volume'])}")

    snap = compute_snapshot(df, sma_fast_window=cfg.strategy.sma_fast_window,
                            sma_slow_window=cfg.strategy.sma_slow_window,
                            dev_z_window=cfg.strategy.dev_z_window)
    if snap is None:
        print("  not enough bars yet for a full snapshot")
        return 0
    print(f"  price={snap.price:.2f}  vwap={snap.vwap:.2f}  dev={snap.vwap_dev_frac*100:+.3f}%"
          f"  z={snap.vwap_dev_z:+.2f}  atr={snap.atr:.3f}")
    print(f"  thrust={snap.is_thrust}  reversal_bar={snap.is_reversal_bar}")

    sig = VwapReversionStrategy(cfg.strategy).evaluate(df)
    print("\n=== SIGNAL ===")
    print(f"  side={sig.side.value}  conf={sig.confidence:.2f}  reason={sig.reason}")
    if sig.is_actionable:
        print(f"  entry={sig.entry_ref:.2f}  target={sig.target:.2f}  stop={sig.stop:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
