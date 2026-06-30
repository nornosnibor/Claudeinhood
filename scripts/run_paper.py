#!/usr/bin/env python3
"""Run the engine against Alpaca PAPER trading.

Usage:
    python -m scripts.run_paper          # or: python scripts/run_paper.py

Requires ALPACA_API_KEY / ALPACA_SECRET_KEY in the environment (.env supported).
This routes orders to the Alpaca paper account only. It does NOT touch Robinhood.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from claudeinhood.broker.alpaca_broker import AlpacaBroker
from claudeinhood.config import load_config
from claudeinhood.data.alpaca_data import AlpacaData
from claudeinhood.engine.runner import Engine
from claudeinhood.risk.manager import RiskManager, RiskState


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    problems = cfg.validate_for_live()
    if problems:
        print("Cannot start:")
        for p in problems:
            print(f"  - {p}")
        return 1

    broker = AlpacaBroker(cfg.alpaca_api_key, cfg.alpaca_secret_key, paper=True)
    data = AlpacaData(cfg.alpaca_api_key, cfg.alpaca_secret_key, feed=cfg.alpaca_data_feed)

    acct = broker.get_account()
    risk = RiskManager(
        cfg.risk,
        RiskState(start_of_day_equity=acct.equity, equity=acct.equity,
                  day=date.today(), settled_cash=acct.settled_cash),
    )

    # TODO(tomorrow): supply a real expiries provider from the Alpaca options
    # chain so 0/1-DTE selection works. Until then, option entries are skipped
    # for lack of a contract/premium, but the signal + risk loop runs live.
    engine = Engine(cfg, broker, data, risk, available_expiries_provider=lambda: [])
    engine.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
