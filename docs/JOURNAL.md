# Trading Journal — predictions, outcomes, lessons

This is the discipline layer. Machine log lives in `journal/trades.jsonl`
(written by `claudeinhood/journal.py`); this file is the human narrative.

**The one number that matters:** predicted win rate vs **realized** win rate.
A widening gap is the 45%→14.7% disease showing up live. When the gap blows out,
we stop and re-diagnose — we do not "wait for it to come back."

---

## Lessons to date (pre-live research)

These come from rigorous backtests on SPY (Alpaca, IEX feed). Logged so we don't
re-learn them with money.

1. **1-min VWAP reversion has no edge.** Fade 49.5% / momentum 48.3% (symmetric
   barriers ≈ coin flip). The most efficient market at the most efficient
   timeframe — dead on arrival.
2. **5-min RSI reversion loses (44%); the momentum inversion looked good (55%)
   then decayed to 52% over 21 months.** Classic regime overfit — the exact
   45%→14.7% trap, caught in backtest this time instead of live.
3. **No simple regime filter rescued it.** Efficiency-ratio (chop filter) didn't
   move the needle; daily-trend alignment made it worse; a fade-in-range /
   ride-in-trend switch was 50.3% over 21 months. The clean 4-month pattern was
   sample luck.
4. **Pivots are regime-mirrored, not edged.** Bounce wins in range months, break
   wins in trend months; aggregate ~50%. Confirms: the market's *character*
   changes, and no static predictive rule wins.
5. **Why ~52% can't pay:** 0DTE option spreads run 5–15% of premium round-trip.
   A raw directional hit rate needs to be well into the high-50s/60s to clear
   that friction. Nothing predictive we tested got there.

**Meta-lesson (from Ronny's prior system + confirmed here):** backtests lie via
regime overfit + execution costs. Trust *structural* signals (defined event +
fixed risk) over *predictive* ones. Prove it lives on paper before funding.
Start simple: one signal, one filter.

---

## Active hypothesis

> **ORB (Opening Range Breakout)** — structural, not predictive. Define the first
> N-minute range; trade a clean break with fixed risk; take 10–30% on the option
> and leave; never hold to expiry. One signal, one filter. Prove it lives.

Risk rules (hardcoded, from Ronny's system):
- Target 10–30% on the option, then OUT. Never hold to expiry.
- Small sizing, quick exits.
- FOMC weeks: size down, faster exits, flat by Tuesday EOD.
- Friday: bank profits early, no new positions after 1:00pm CST.
- **TODO:** explicit max-loss-per-contract exit (the downside number).

---

## Log

<!-- newest first. Each live/paper trade: prediction -> outcome -> lesson. -->

_(none yet — fills in once paper trading starts)_
