# Claudeinhood

A VWAP-reversion intraday scalping engine for SPY (0/1-DTE options) and liquid
single names. It detects when price **over-extends away from session VWAP on an
exhausted thrust** and fades the move back toward VWAP.

> ⚠️ **This trades real money and can lose all of it.** Options can expire
> worthless the same day. Validate on paper first. Past backtest edge does not
> guarantee future results. Nothing here is financial advice.

## Design principles

1. **Deterministic rules engine, no LLM in the live loop.** Scalping needs
   sub-second reactions; an LLM can't sit in that path. Claude builds, backtests,
   and tunes the engine — the engine executes.
2. **Broker-agnostic.** Strategy/risk/engine talk to a `Broker` interface.
   Alpaca paper is used for validation today; Robinhood drops in for live
   execution by implementing one adapter — nothing else changes.
3. **Risk first.** A hard daily loss cap halts trading, positions are sized to a
   per-trade risk budget, and a cash account's settlement is tracked so you don't
   trip a good-faith violation.
4. **Prove the edge before risking money.** Backtest → Alpaca paper → live.

## Architecture

```
claudeinhood/
  data/         indicators.py (VWAP/SMA/ATR/z-score — pure), alpaca_data.py
  strategy/     base.py (Signal), vwap_reversion.py (the overreaction fade)
  options/      selector.py (pure), alpaca_options.py (live chain + quotes)
  flow/         base.py (FlowFilter veto), probors.py (REST adapter stub)
  risk/         manager.py (daily stop, sizing, settlement)
  broker/       base.py (interface), alpaca_broker.py, robinhood_broker.py (stub)
  engine/       runner.py (data -> strategy -> flow veto -> risk -> order -> exits)
  backtest/     backtester.py (replay sessions, measure edge)
scripts/        run_paper.py, backtest.py
tests/          pure-logic + engine wiring tests (35 passing)
```

## The strategy

`VwapReversionStrategy` fires only when **all** hold:

- VWAP deviation z-score exceeds a threshold (price is statistically stretched);
- the latest bar is a **thrust** (large range + volume spike) that then shows a
  **reversal bar** (exhaustion) — i.e. it looks like an *overreaction*, not a
  trend leg;
- a trend filter (fast vs slow SMA) isn't strongly against the fade.

Entry fades toward VWAP; exit targets a fraction of the distance back to VWAP
with an ATR-based stop and a time stop.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your Alpaca keys

pytest -q                     # run the unit tests

# backtest the signal on history (proves edge before paper)
python scripts/backtest.py SPY 2026-06-01 2026-06-27

# run live against Alpaca PAPER (no real money, no Robinhood)
python scripts/run_paper.py
```

## Flow confirmation (ProBors)

`flow/` adds an optional veto: before fading a stretched move, the engine checks
"where the money's going." If strong **same-direction** options/whale flow is
behind the move, it's probably real (not an overreaction) and the trade is
vetoed. Missing/stale flow data fails open (never blocks).

Important: the live engine needs ProBors' **REST API + key** — it cannot call
the ProBors **MCP** server (MCP tools are interactive, not callable from the
standalone engine). Congressional-trade data is legally delayed (~45 days) and
is *not* used for intraday; only timely flow (options/dark-pool/whale) feeds the
veto. Configure `PROBORS_API_KEY` + `PROBORS_FLOW_ENDPOINT`; otherwise a
`NullFlowFilter` runs and never vetoes.

## Shadow / dry-run mode

Set `DRY_RUN=true` to run the full loop live (real data, real signals) but place
**no orders** — it just logs what it *would* do. Best way to watch the strategy
think before risking anything.

## Roadmap to live

- [x] Indicators, strategy, risk, backtester, broker abstraction
- [x] Alpaca options provider (live chain + quotes + greeks)
- [x] Flow veto layer + ProBors REST adapter scaffold
- [x] Dry-run/shadow mode
- [ ] **Data tier**: confirm Alpaca feed (IEX vs SIP). SIP better for VWAP.
- [ ] **ProBors**: drop in API key + confirm the flow endpoint/field mapping
      (`flow/probors.py:_map_response`).
- [ ] **Backtest + paper validation**: tune `VwapReversionParams`; confirm
      positive expectancy net of slippage.
- [ ] **Robinhood adapter**: implement `RobinhoodBroker` (robin_stocks or MCP).
- [ ] **Go live small** with the 25% daily stop enforced.

## Notes for a $500 account

- One SPY 0DTE contract is ~$30–$300, so sizing is 1–2 contracts. The risk
  manager will return 0 contracts rather than oversize — that's expected.
- Cash account: option sale proceeds settle T+1; the engine only spends settled
  cash to avoid good-faith violations.
- The PDT $25k rule was repealed (effective 2026-06-04), so day-trade count is
  not a constraint.
