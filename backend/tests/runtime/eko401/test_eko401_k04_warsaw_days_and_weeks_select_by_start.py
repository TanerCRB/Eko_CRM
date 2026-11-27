"""EKO-4-01 K-04 (ADR-0002 *Europe/Warsaw days*, ADR-0002-C8; ADR-0001 Constraint 3; DSH-2): a day
and a week select exactly the visits whose start falls in them, by half-open Europe/Warsaw ranges
computed in the application with `zoneinfo`, the 23-hour and 25-hour days included.

The request names Warsaw calendar dates; the process and database session zones are UTC (the
process's where the platform lets a test set it). The range function's own unit test is
`tests/unit/test_eko401_k04_warsaw_ranges.py`; the image half of C8 is
`tests/runtime/test_eko401_k04_warsaw_zone_in_the_image.py`. Runtime, on real PostgreSQL and the
OIDC stub; every value is synthetic.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.eko201.conftest import Browser, FakeClock
from tests.runtime.eko301.conftest import REP_A, Crm
from tests.runtime.eko401.conftest import (
    EMPTY,
    PERIOD,
    all_visits,
    customer,
    ids,
    items,
    period,
    planned,
    status_and_json,
    visit_body,
)

pytestmark = pytest.mark.runtime


@pytest.fixture(autouse=True)
def process_zone_utc(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()
    yield
    monkeypatch.undo()
    if hasattr(time, "tzset"):
        time.tzset()


@pytest.fixture
def rep(crm: Crm) -> tuple[Browser, str]:
    rep_a = crm.login(REP_A, ["rep"])
    return rep_a, customer(rep_a, "Gospodarstwo K04")


def at(browser: Browser, customer_id: str, day: str, start: str, end: str) -> dict[str, Any]:
    return planned(browser, visit_body(customer_id, (day, start), (day, end)))


AUTUMN = {
    "midnight": ("2026-10-25", "00:00", "00:30", "2026-10-24T22:00:00Z"),
    "last-half-hour": ("2026-10-25", "23:30", "23:45", "2026-10-25T22:30:00Z"),
    "next-midnight": ("2026-10-26", "00:00", "00:30", "2026-10-25T23:00:00Z"),
    "day-before-late": ("2026-10-24", "23:30", "23:45", "2026-10-24T21:30:00Z"),
}
SPRING = {
    "early": ("2026-03-29", "00:30", "01:00", "2026-03-28T23:30:00Z"),
    "late": ("2026-03-29", "23:30", "23:45", "2026-03-29T21:30:00Z"),
    "next-early": ("2026-03-30", "00:30", "01:00", "2026-03-29T22:30:00Z"),
}


Case = tuple[str, str, str, str]


def plant(browser: Browser, customer_id: str, cases: dict[str, Case]) -> dict[str, str]:
    made = {}
    for name, (day, start, end, starts_at) in cases.items():
        created = at(browser, customer_id, day, start, end)
        assert created["starts_at"] == starts_at, name
        made[name] = created["id"]
    return made


def test_k04_the_25_hour_day_holds_its_first_and_last_minutes_and_not_the_next_midnight(
    rep: tuple[Browser, str],
) -> None:
    browser, customer_id = rep
    made = plant(browser, customer_id, AUTUMN)
    assert set(ids(period(browser, "2026-10-25"))) == {made["midnight"], made["last-half-hour"]}
    # Contrast: the next midnight's visit, changing only the requested day, appears there only.
    assert ids(period(browser, "2026-10-26")) == [made["next-midnight"]]
    assert ids(period(browser, "2026-10-24")) == [made["day-before-late"]]


def test_k04_the_23_hour_day_holds_its_visits_and_not_the_next_days(
    rep: tuple[Browser, str],
) -> None:
    browser, customer_id = rep
    made = plant(browser, customer_id, SPRING)
    assert set(ids(period(browser, "2026-03-29"))) == {made["early"], made["late"]}
    assert ids(period(browser, "2026-03-30")) == [made["next-early"]]
    # A visit at 00:30 Warsaw is on its Warsaw day, not on the UTC date of its start.
    assert made["early"] not in ids(period(browser, "2026-03-28"))


def test_k04_every_visit_falls_on_exactly_one_day(rep: tuple[Browser, str]) -> None:
    browser, customer_id = rep
    made = {**plant(browser, customer_id, AUTUMN), **plant(browser, customer_id, SPRING)}
    days = [f"2026-10-{d}" for d in range(23, 28)] + [f"2026-03-{d}" for d in range(27, 32)]
    seen: dict[str, list[str]] = {visit_id: [] for visit_id in made.values()}
    for day in days:
        for visit_id in ids(period(browser, day)):
            seen[visit_id].append(day)
    assert all(len(found) == 1 for found in seen.values()), seen


def test_k04_the_week_holds_the_last_half_hour_of_its_sunday_and_not_the_next_monday(
    rep: tuple[Browser, str],
) -> None:
    browser, customer_id = rep
    made = plant(browser, customer_id, AUTUMN)
    week = ids(period(browser, "2026-10-19", "2026-10-25"))
    assert set(week) == {made["midnight"], made["last-half-hour"], made["day-before-late"]}
    assert made["next-midnight"] not in week


def test_k04_edge_lists_are_in_start_order_and_ties_appear_once_each(
    rep: tuple[Browser, str],
) -> None:
    browser, customer_id = rep
    day = "2026-11-30"
    late = at(browser, customer_id, day, "15:00", "16:00")["id"]
    tie_one = at(browser, customer_id, day, "09:00", "10:00")["id"]
    tie_two = at(browser, customer_id, day, "09:00", "09:30")["id"]
    early = at(browser, customer_id, day, "07:00", "08:00")["id"]
    for listed in (period(browser, day), period(browser, "2026-11-30", "2026-12-06")):
        found = ids(listed)
        assert found[0] == early and found[-1] == late
        assert sorted(found[1:3]) == sorted([tie_one, tie_two])
        assert len(found) == 4
    starts = [item["starts_at"] for item in items(all_visits(browser))]
    assert starts == sorted(starts)


def test_k04_edge_a_cross_day_visit_appears_only_on_its_starts_day(
    rep: tuple[Browser, str],
) -> None:
    browser, customer_id = rep
    created = planned(
        browser, visit_body(customer_id, ("2026-11-30", "23:00"), ("2026-12-01", "01:00"))
    )
    assert ids(period(browser, "2026-11-30")) == [created["id"]]
    assert ids(period(browser, "2026-12-01")) == []


def test_k04_edge_an_empty_day_or_week_is_an_empty_list(rep: tuple[Browser, str]) -> None:
    browser, _ = rep
    assert status_and_json(period(browser, "2026-12-24")) == (200, EMPTY)
    assert status_and_json(period(browser, "2026-12-21", "2026-12-27")) == (200, EMPTY)


INVALID_PERIODS: dict[str, tuple[dict[str, str], list[list[str]]]] = {
    "impossible-first": ({"first": "2026-02-30", "last": "2026-03-01"}, [["query", "first"]]),
    "impossible-last": ({"first": "2026-02-01", "last": "2026-02-30"}, [["query", "last"]]),
    "instant": ({"first": "2026-10-25T00:00:00Z", "last": "2026-10-25"}, [["query", "first"]]),
    "no-dashes": ({"first": "20261025", "last": "2026-10-25"}, [["query", "first"]]),
    "spaced": ({"first": " 2026-10-25", "last": "2026-10-25"}, [["query", "first"]]),
    "empty": ({"first": "", "last": "2026-10-25"}, [["query", "first"]]),
    "missing-last": ({"first": "2026-10-25"}, [["query", "last"]]),
    "missing-both": ({}, [["query", "first"], ["query", "last"]]),
    "last-before-first": ({"first": "2026-10-26", "last": "2026-10-25"}, [["query", "last"]]),
    "first-day-of-the-calendar": (
        {"first": "0001-01-01", "last": "0001-01-01"},
        [["query", "first"]],
    ),  # fmt: skip
    "last-day-of-the-calendar": (
        {"first": "9999-12-31", "last": "9999-12-31"},
        [["query", "last"]],
    ),  # fmt: skip
}


@pytest.mark.parametrize("case", sorted(INVALID_PERIODS))
def test_k04_edge_an_invalid_date_is_a_422_naming_the_parameter(
    rep: tuple[Browser, str], case: str
) -> None:
    browser, _ = rep
    params, locs = INVALID_PERIODS[case]
    response = browser.send("GET", PERIOD, params=params)
    assert response.status_code == 422, response.text
    assert [e["loc"] for e in response.json()["detail"]] == locs
    for value in params.values():
        if value.strip():
            assert value.strip() not in response.text


def test_k04_edge_the_all_visits_list_holds_past_and_future_visits(
    rep: tuple[Browser, str], clock: FakeClock
) -> None:
    browser, customer_id = rep
    past = at(browser, customer_id, "2026-01-05", "10:00", "11:00")
    future = at(browser, customer_id, "2027-06-01", "10:00", "11:00")
    listed = items(all_visits(browser))
    assert [v["id"] for v in listed] == [past["id"], future["id"]]
    assert [v["state"] for v in listed] == ["held", "planned"]
