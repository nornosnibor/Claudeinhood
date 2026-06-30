from claudeinhood.exits import premium_exit


def test_target_hit():
    reason, pnl = premium_exit(1.00, 1.25, target_pct=0.20, stop_pct=0.22)
    assert reason == "target" and round(pnl, 2) == 0.25


def test_stop_hit():
    reason, pnl = premium_exit(1.00, 0.75, target_pct=0.20, stop_pct=0.22)
    assert reason == "stop" and round(pnl, 2) == -0.25


def test_hold_in_between():
    reason, pnl = premium_exit(1.00, 1.10, target_pct=0.20, stop_pct=0.22)
    assert reason is None and round(pnl, 2) == 0.10


def test_just_past_thresholds():
    assert premium_exit(1.00, 1.21, target_pct=0.20, stop_pct=0.22)[0] == "target"
    assert premium_exit(1.00, 0.77, target_pct=0.20, stop_pct=0.22)[0] == "stop"


def test_guard_bad_entry():
    assert premium_exit(0.0, 1.0, target_pct=0.2, stop_pct=0.22) == (None, 0.0)
