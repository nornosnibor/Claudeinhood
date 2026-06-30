from datetime import datetime, timezone, timedelta

from claudeinhood.session_rules import (
    SessionRules,
    can_enter,
    is_fomc_week,
    must_flat,
    size_multiplier,
)

ET = timezone(timedelta(hours=-4))  # ET in summer (DST); fine for logic tests


def dt(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


R = SessionRules()


def test_entry_blocked_before_or_complete():
    ok, why = can_enter(dt(2026, 7, 1, 9, 40), R)  # before 9:45
    assert not ok and "opening range" in why


def test_entry_ok_midmorning_normal_day():
    ok, _ = can_enter(dt(2026, 7, 1, 10, 30), R)  # Wed, not fomc
    assert ok


def test_entry_blocked_after_daily_cutoff():
    ok, why = can_enter(dt(2026, 7, 1, 13, 45), R)
    assert not ok and "cutoff" in why


def test_friday_entries_follow_daily_cutoff_and_flat_early():
    # Daily 13:30 cutoff already enforces "no new after 1pm CST"; Friday's
    # special behavior is the early force-flat at 2pm ET.
    assert can_enter(dt(2026, 7, 3, 13, 0), R)[0]            # Fri 1:00pm ok
    assert not can_enter(dt(2026, 7, 3, 13, 30), R)[0]       # Fri past daily cutoff
    assert must_flat(dt(2026, 7, 3, 14, 0), R)               # Fri flat by 2pm ET
    assert not must_flat(dt(2026, 7, 1, 14, 0), R)           # Wed still holds


def test_fomc_week_detection_and_sizing():
    # 2026-06-17 is an FOMC announcement; the week Mon 6/15..Fri 6/19.
    assert is_fomc_week(dt(2026, 6, 16, 10, 0).date(), R)
    assert size_multiplier(dt(2026, 6, 16, 10, 0).date(), R) == 0.5
    assert size_multiplier(dt(2026, 7, 1, 10, 0).date(), R) == 1.0


def test_fomc_announcement_day_late_morning_blocked():
    ok, why = can_enter(dt(2026, 6, 17, 11, 30), R)  # announcement day, 11:30
    assert not ok and "fomc" in why


def test_must_flat_force_close():
    assert not must_flat(dt(2026, 7, 1, 15, 30), R)
    assert must_flat(dt(2026, 7, 1, 15, 45), R)
    assert must_flat(dt(2026, 7, 3, 14, 0), R)  # friday earlier
