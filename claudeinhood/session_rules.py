"""Session timing / event guards — Ronny's hardcoded rules, as pure functions.

All times are US/Eastern. 1:00pm CST = 2:00pm ET.

Rules encoded:
  * No new entries before the opening range completes or after the daily cutoff.
  * Friday: bank early, no new positions after 1:00pm CST (2:00pm ET), flat sooner.
  * FOMC week: size down; on the announcement day, no new entries after late
    morning; be flat by Tuesday EOD (i.e. avoid the Wed announcement-day churn).
  * Never hold to expiry: a hard force-flat time well before the close.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

# FOMC announcement days (Wednesdays). 2026 schedule — APPROXIMATE, update from
# federalreserve.gov before relying on it.
FOMC_ANNOUNCEMENTS = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
]


@dataclass(frozen=True)
class SessionRules:
    or_minutes: int = 15
    session_open: time = time(9, 30)
    entry_end: time = time(13, 30)         # daily cutoff (=12:30 CST, already
                                           # earlier than Friday's "1pm CST" rule)
    force_flat: time = time(15, 45)        # never hold to expiry
    friday_force_flat: time = time(14, 0)  # Friday: bank early, flat by 1pm CST
    fomc_size_mult: float = 0.5
    fomc_announce_entry_end: time = time(11, 0)
    fomc_dates: tuple[date, ...] = field(default_factory=lambda: tuple(FOMC_ANNOUNCEMENTS))

    @property
    def entry_start(self) -> time:
        dt = datetime.combine(date.today(), self.session_open) + timedelta(minutes=self.or_minutes)
        return dt.time()


def is_fomc_week(d: date, rules: SessionRules) -> bool:
    """True if d falls in the Mon–Fri week containing an FOMC announcement."""
    for ann in rules.fomc_dates:
        monday = ann - timedelta(days=ann.weekday())
        if monday <= d <= monday + timedelta(days=4):
            return True
    return False


def is_fomc_announcement_day(d: date, rules: SessionRules) -> bool:
    return d in rules.fomc_dates


def size_multiplier(d: date, rules: SessionRules) -> float:
    """Position-size scale for the day (FOMC week => size down)."""
    return rules.fomc_size_mult if is_fomc_week(d, rules) else 1.0


def can_enter(now: datetime, rules: SessionRules) -> tuple[bool, str]:
    """Whether a NEW entry is allowed at `now` (tz-aware ET)."""
    d, t = now.date(), now.time()
    if t < rules.entry_start:
        return False, "opening range not complete"
    # FOMC announcement day: stop entering before the print churn.
    if is_fomc_announcement_day(d, rules) and t >= rules.fomc_announce_entry_end:
        return False, "fomc announcement day: no new entries late morning"
    if t >= rules.entry_end:
        return False, "past daily entry cutoff"
    return True, "ok"


def must_flat(now: datetime, rules: SessionRules) -> bool:
    """Hard force-flat: never hold to expiry; earlier on Fridays."""
    d, t = now.date(), now.time()
    if d.weekday() == 4 and t >= rules.friday_force_flat:
        return True
    return t >= rules.force_flat
