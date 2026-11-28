"""EKO-4-01 K-04, the range function alone (ADR-0002 *Europe/Warsaw days*, ADR-0002-C8): a run of
Warsaw calendar dates becomes one half-open instant range computed with `zoneinfo`, so the
2026-10-25 day is 25 hours, the 2026-03-29 day 23 and the week holding the first 7 x 24 + 1. The
HTTP half is `tests/runtime/eko401/test_eko401_k04_warsaw_days_and_weeks_select_by_start.py`.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain import warsaw

HOUR = timedelta(hours=1)


def days(first: str, last: str | None = None) -> warsaw.Period:
    return warsaw.period_of(date.fromisoformat(first), date.fromisoformat(last or first))


@pytest.mark.parametrize(
    ("day", "hours"),
    [("2026-10-25", 25), ("2026-03-29", 23), ("2026-11-30", 24), ("2026-07-01", 24)],
)
def test_k04_c8_a_day_is_its_warsaw_length(day: str, hours: int) -> None:
    found = days(day)
    assert found.ends - found.starts == hours * HOUR


def test_k04_c8_the_25_hour_day_starts_and_ends_at_its_warsaw_midnights() -> None:
    found = days("2026-10-25")
    assert found.starts == datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    assert found.ends == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


def test_k04_c8_the_23_hour_day_starts_and_ends_at_its_warsaw_midnights() -> None:
    found = days("2026-03-29")
    assert found.starts == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
    assert found.ends == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)


def test_k04_c8_the_week_holding_the_25_hour_day_is_169_hours() -> None:
    found = days("2026-10-19", "2026-10-25")
    assert found.starts == datetime(2026, 10, 18, 22, 0, tzinfo=UTC)
    assert found.ends - found.starts == (7 * 24 + 1) * HOUR


def test_k04_c8_ranges_are_half_open_one_day_ending_where_the_next_starts() -> None:
    first, second = days("2026-10-25"), days("2026-10-26")
    assert first.ends == second.starts
    assert first.holds(first.starts) and not first.holds(first.ends)
    assert second.holds(first.ends)


@pytest.mark.parametrize(
    ("first", "last", "refused"),
    [("2026-10-26", "2026-10-25", "last"), ("0001-01-01", "0001-01-02", "first"),
     ("9999-12-30", "9999-12-31", "last")],
)  # fmt: skip
def test_k04_c8_edge_a_period_with_no_instants_is_refused_naming_its_bound(
    first: str, last: str, refused: str
) -> None:
    with pytest.raises(warsaw.PeriodRefused) as error:
        days(first, last)
    assert error.value.bound == refused
