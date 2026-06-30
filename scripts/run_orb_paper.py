#!/usr/bin/env python3
"""Run the ORB paper engine on SPY against Alpaca PAPER. Logs predict->outcome
to the journal. Places NO real-money orders; does not touch Robinhood.

    DRY_RUN=true  python scripts/run_orb_paper.py     # observe only
    python scripts/run_orb_paper.py                   # paper trades
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from claudeinhood.broker.alpaca_broker import AlpacaBroker
from claudeinhood.config import load_config
from claudeinhood.data.alpaca_data import AlpacaData
from claudeinhood.engine.orb_engine import ORBPaperEngine
from claudeinhood.journal import Journal
from claudeinhood.options.alpaca_options import AlpacaOptions
from claudeinhood.risk.manager import RiskManager, RiskState


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    cfg.primary_symbol = "SPY"
    problems = cfg.validate_for_live()
    if problems:
        print("Cannot start:", "; ".join(problems))
        return 1

    broker = AlpacaBroker(cfg.alpaca_api_key, cfg.alpaca_secret_key, paper=True)
    data = AlpacaData(cfg.alpaca_api_key, cfg.alpaca_secret_key, feed=cfg.alpaca_data_feed)
    options = AlpacaOptions(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    journal = Journal("journal/orb_spy.jsonl")

    acct = broker.get_account()
    # Size as if the account were $500 even though paper seeds $100k, so behavior
    # matches the real plan.
    sim_equity = float(os.getenv("SIM_EQUITY", "500"))
    risk = RiskManager(cfg.risk, RiskState(
        start_of_day_equity=sim_equity, equity=sim_equity, day=date.today(),
        settled_cash=min(sim_equity, acct.settled_cash)))

    print(f"ORB paper on SPY | dry_run={cfg.dry_run} | sized as ${sim_equity:.0f} "
          f"| target +{cfg.target_premium_pct*100:.0f}% stop -{cfg.stop_premium_pct*100:.0f}%")
    ORBPaperEngine(cfg, broker, data, options, risk, journal).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
