"""Prediction -> outcome -> lesson log.

The point (per the 45%-backtest / 14.7%-live lesson): record what the system
*predicts* at entry, then reconcile against what actually *happened*, so the
backtest-vs-reality gap shows up live and early — not after the account's funded.

Storage is append-only JSONL (machine-readable, audit-friendly). `summarize()`
computes the number that matters most: predicted win rate vs realized win rate,
overall and by strategy/regime. A widening gap = decay/overfit, stop trading.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Prediction:
    """Logged at entry — the falsifiable claim."""
    id: str
    strategy: str
    symbol: str
    side: str                       # long / short
    underlying_entry: float
    target: float                   # underlying level we expect to reach
    stop: float
    thesis: str                     # why, in one line
    predicted: str = "target"       # what we expect: target | stop
    option_symbol: Optional[str] = None
    entry_premium: Optional[float] = None
    target_premium_pct: Optional[float] = None   # e.g. 0.20 for +20%
    regime: Optional[str] = None
    confidence: Optional[float] = None
    ts: str = field(default_factory=_now)
    kind: str = "prediction"


@dataclass
class Outcome:
    """Logged at exit — what actually happened."""
    id: str                         # matches the Prediction id
    result: str                     # target | stop | time | scratch
    exit_premium: Optional[float] = None
    pnl_pct: Optional[float] = None  # realized option P&L %
    underlying_exit: Optional[float] = None
    lesson: str = ""
    ts: str = field(default_factory=_now)
    kind: str = "outcome"


class Journal:
    def __init__(self, path: str | Path = "journal/trades.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, obj) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(obj)) + "\n")

    def predict(self, p: Prediction) -> None:
        self._append(p)

    def resolve(self, o: Outcome) -> None:
        self._append(o)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def summarize(self) -> dict:
        rows = self._load()
        preds = {r["id"]: r for r in rows if r.get("kind") == "prediction"}
        outs = {r["id"]: r for r in rows if r.get("kind") == "outcome"}

        resolved = [(preds[i], outs[i]) for i in preds if i in outs]
        n_pred, n_res = len(preds), len(resolved)
        wins = [o for _, o in resolved if o["result"] == "target"]
        realized_wr = (len(wins) / n_res * 100) if n_res else 0.0
        # "predicted win rate" = share of resolved trades the system expected to win
        predicted_wins = [p for p, _ in resolved if p.get("predicted") == "target"]
        predicted_wr = (len(predicted_wins) / n_res * 100) if n_res else 0.0
        pnls = [o["pnl_pct"] for _, o in resolved if o.get("pnl_pct") is not None]
        avg_pnl = (sum(pnls) / len(pnls) * 100) if pnls else 0.0

        return {
            "predictions": n_pred,
            "resolved": n_res,
            "open": n_pred - n_res,
            "predicted_win_rate": round(predicted_wr, 1),
            "realized_win_rate": round(realized_wr, 1),
            "gap": round(predicted_wr - realized_wr, 1),  # the decay alarm
            "avg_pnl_pct": round(avg_pnl, 2),
        }

    def render_markdown(self) -> str:
        s = self.summarize()
        return (
            f"Predictions: {s['predictions']} | resolved: {s['resolved']} | open: {s['open']}\n"
            f"Predicted WR: {s['predicted_win_rate']}%  Realized WR: {s['realized_win_rate']}%  "
            f"**Gap: {s['gap']} pts**  Avg P&L/trade: {s['avg_pnl_pct']}%\n"
        )
