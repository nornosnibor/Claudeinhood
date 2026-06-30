import tempfile
from pathlib import Path

from claudeinhood.journal import Journal, Outcome, Prediction


def _journal():
    d = tempfile.mkdtemp()
    return Journal(Path(d) / "trades.jsonl")


def _pred(i, predicted="target"):
    return Prediction(id=i, strategy="orb", symbol="SPY", side="long",
                      underlying_entry=540.0, target=541.0, stop=539.5,
                      thesis="break of OR high", predicted=predicted,
                      target_premium_pct=0.20, regime="trend")


def test_predict_then_resolve_roundtrip():
    j = _journal()
    j.predict(_pred("t1"))
    j.resolve(Outcome(id="t1", result="target", pnl_pct=0.22, lesson="clean break held"))
    s = j.summarize()
    assert s["predictions"] == 1
    assert s["resolved"] == 1
    assert s["open"] == 0
    assert s["realized_win_rate"] == 100.0


def test_open_prediction_counts():
    j = _journal()
    j.predict(_pred("t1"))
    j.predict(_pred("t2"))
    j.resolve(Outcome(id="t1", result="stop", pnl_pct=-0.30))
    s = j.summarize()
    assert s["resolved"] == 1 and s["open"] == 1
    assert s["realized_win_rate"] == 0.0


def test_gap_flags_overfit():
    # Predicted all winners, half actually lost -> 50-point gap (the alarm).
    j = _journal()
    for k in range(4):
        j.predict(_pred(f"t{k}", predicted="target"))
    j.resolve(Outcome(id="t0", result="target", pnl_pct=0.2))
    j.resolve(Outcome(id="t1", result="target", pnl_pct=0.2))
    j.resolve(Outcome(id="t2", result="stop", pnl_pct=-0.3))
    j.resolve(Outcome(id="t3", result="stop", pnl_pct=-0.3))
    s = j.summarize()
    assert s["predicted_win_rate"] == 100.0
    assert s["realized_win_rate"] == 50.0
    assert s["gap"] == 50.0


def test_avg_pnl():
    j = _journal()
    j.predict(_pred("t1"))
    j.resolve(Outcome(id="t1", result="target", pnl_pct=0.10))
    assert j.summarize()["avg_pnl_pct"] == 10.0
