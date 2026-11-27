"""Europe/Warsaw wall times and days (ADR-0002 *Wall time entered by a user*, ADR-0002-C15, and
*Europe/Warsaw days*, ADR-0002-C8).

The one domain function that resolves a wall time a user typed (a local date and a local time,
no offset) to an instant, and the one that turns a run of Warsaw calendar dates into a half-open
instant range. Both use `zoneinfo` only: no fixed offset, and no time-zone arithmetic is left to
the database, which receives the range's two instants. Every instant returned is UTC.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
OUTSIDE = "outside the dates the application can hold"


class WallTimeReason(StrEnum):
    """Why a typed local time has no one instant: the clocks skip it (the spring change) or
    repeat it (the autumn change). A stable machine value; the API names it per field."""

    NONEXISTENT = "nonexistent"
    AMBIGUOUS = "ambiguous"


# Fixed texts that never repeat the typed time (ADR-0005; ADR-0003 gate-2 rules: no echo).
REASON_TEXTS = {
    WallTimeReason.NONEXISTENT: "this local time does not exist in Europe/Warsaw (clocks skip it)",
    WallTimeReason.AMBIGUOUS: "this local time occurs twice in Europe/Warsaw (clocks repeat it)",
}


class WallTimeRefused(ValueError):
    """A typed local time with no one instant, carrying which of the two reasons applies."""

    def __init__(self, reason: WallTimeReason) -> None:
        super().__init__(REASON_TEXTS[reason])
        self.reason = reason


class PeriodRefused(ValueError):
    """A run of dates with no instant range: `bound` names the date ("first" or "last") that
    is refused."""

    def __init__(self, bound: str, message: str) -> None:
        super().__init__(message)
        self.bound = bound


@dataclass(frozen=True)
class Period:
    """A half-open instant range: `starts` is in it, `ends` is not."""

    starts: datetime
    ends: datetime

    def holds(self, instant: datetime) -> bool:
        return self.starts <= instant < self.ends


def _local(day: date, at: time, fold: int) -> datetime:
    return datetime.combine(day, at, tzinfo=WARSAW).replace(fold=fold)


def instant_of(day: date, at: time) -> datetime:
    """The one instant of a Europe/Warsaw local date and time. Both folds are tried: a time the
    clocks skip maps back to a different wall time under either fold, and one they repeat maps
    to two different instants (ADR-0002-C15). `at` is a wall time with no zone and no seconds
    the API would not accept."""
    if at.tzinfo is not None:
        raise ValueError("a wall time carries no zone")
    wall = datetime.combine(day, at)
    try:
        first, second = (_local(day, at, fold).astimezone(UTC) for fold in (0, 1))
    except OverflowError:
        raise ValueError(OUTSIDE) from None
    back = [i.astimezone(WARSAW).replace(tzinfo=None) for i in (first, second)]
    if wall not in back:
        raise WallTimeRefused(WallTimeReason.NONEXISTENT)
    if first != second:
        raise WallTimeRefused(WallTimeReason.AMBIGUOUS)
    return first


def _midnight(day: date) -> datetime:
    # No Warsaw midnight is skipped or repeated: the changes are at 02:00 and 03:00.
    return datetime.combine(day, time(0), tzinfo=WARSAW).astimezone(UTC)


def period_of(first: date, last: date) -> Period:
    """The half-open range from the Warsaw midnight that starts `first` to the one that ends
    `last`, both dates included: a day is 23, 24 or 25 hours, as Warsaw has it (ADR-0002-C8).
    The end is the next date's midnight, never the start plus 24 hours per day."""
    if last < first:
        raise PeriodRefused("last", "the last date is before the first")
    try:
        starts = _midnight(first)
    except OverflowError:
        raise PeriodRefused("first", OUTSIDE) from None
    try:
        ends = _midnight(last + timedelta(days=1))
    except OverflowError:
        raise PeriodRefused("last", OUTSIDE) from None
    return Period(starts, ends)
