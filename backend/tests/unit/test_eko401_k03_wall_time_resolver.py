"""EKO-4-01 K-03, the resolver alone (ADR-0002 *Wall time entered by a user*, ADR-0002-C15): one
domain function turns a Europe/Warsaw local date and time into an instant, trying both folds, and
refuses a time the clocks skip or repeat with its own reason. The HTTP half is
`tests/runtime/eko401/test_eko401_k03_wall_times_resolved_or_refused_with_their_reason.py`.
"""

from datetime import UTC, date, datetime, time

import pytest

from app.domain import warsaw


def resolved(day: str, at: str) -> datetime:
    return warsaw.instant_of(date.fromisoformat(day), time.fromisoformat(at))


@pytest.mark.parametrize(
    ("day", "at", "expected"),
    [
        ("2026-10-25", "01:30", datetime(2026, 10, 24, 23, 30, tzinfo=UTC)),
        ("2026-10-25", "03:30", datetime(2026, 10, 25, 2, 30, tzinfo=UTC)),
        ("2026-03-29", "03:00", datetime(2026, 3, 29, 1, 0, tzinfo=UTC)),
        ("2026-03-29", "01:59", datetime(2026, 3, 29, 0, 59, tzinfo=UTC)),
        ("2026-11-30", "10:00", datetime(2026, 11, 30, 9, 0, tzinfo=UTC)),
        ("2026-07-01", "10:00", datetime(2026, 7, 1, 8, 0, tzinfo=UTC)),
    ],
)
def test_k03_an_unambiguous_local_time_resolves_to_its_one_instant(
    day: str, at: str, expected: datetime
) -> None:
    found = resolved(day, at)
    assert found == expected
    assert found.utcoffset() is not None and found.tzinfo is UTC


@pytest.mark.parametrize("at", ["02:00", "02:30", "02:59"])
def test_k03_a_time_the_spring_clocks_skip_is_nonexistent(at: str) -> None:
    with pytest.raises(warsaw.WallTimeRefused) as refused:
        resolved("2026-03-29", at)
    assert refused.value.reason is warsaw.WallTimeReason.NONEXISTENT


@pytest.mark.parametrize("at", ["02:00", "02:30", "02:59"])
def test_k03_a_time_the_autumn_clocks_repeat_is_ambiguous(at: str) -> None:
    with pytest.raises(warsaw.WallTimeRefused) as refused:
        resolved("2026-10-25", at)
    assert refused.value.reason is warsaw.WallTimeReason.AMBIGUOUS


def test_k03_the_two_reasons_are_two_values_and_messages_that_name_no_time() -> None:
    reasons = {reason.value for reason in warsaw.WallTimeReason}
    assert reasons == {"nonexistent", "ambiguous"}
    messages = {str(warsaw.WallTimeRefused(reason)) for reason in warsaw.WallTimeReason}
    assert len(messages) == 2
    assert not any(ch.isdigit() for message in messages for ch in message)


def test_k03_edge_a_local_time_with_no_instant_is_refused_as_a_value_not_an_overflow() -> None:
    # Midnight of the first calendar day in Warsaw is before the first UTC instant Python holds.
    with pytest.raises(ValueError, match="outside") as refused:
        resolved("0001-01-01", "00:00")
    assert not isinstance(refused.value, warsaw.WallTimeRefused)
    # Contrast: the last minute of the calendar has its instant.
    assert resolved("9999-12-31", "23:59") == datetime(9999, 12, 31, 22, 59, tzinfo=UTC)
