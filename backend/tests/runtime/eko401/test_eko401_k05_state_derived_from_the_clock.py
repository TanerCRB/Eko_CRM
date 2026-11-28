"""EKO-4-01 K-05 (glossary *Visit states*; ADR-0002 *Now, today*, ADR-0002-C13): a visit is Planned
until its end instant and Held from it on, derived at read time from the application's injected
clock and never stored.

The application's clock is a fake of its own here, apart from the one the login and the OIDC stub
share, so moving it changes nothing but "now" for the visit operations. A schema test finds no
column of the visit table that could hold a state. Runtime, on real PostgreSQL and the OIDC stub;
every value is synthetic.
"""

from datetime import UTC, datetime

import pytest

from tests.runtime.eko201.conftest import Browser, FakeClock
from tests.runtime.eko301.conftest import MANAGER, REP_A, Crm
from tests.runtime.eko401.conftest import (
    VISIT_COLUMNS,
    all_visits,
    customer,
    items,
    period,
    planned,
    raw_visit_row,
    read_visit,
    visit_body,
)

pytestmark = pytest.mark.runtime

DAY = "2026-11-30"
# 10:00 to 11:00 Warsaw (CET) is 09:00Z to 10:00Z.
ENDS_AT = datetime(2026, 11, 30, 10, 0, tzinfo=UTC)


def states(browser: Browser, visit_id: str) -> set[str]:
    """The state every read answers for the visit: by identifier, the day, the week and all."""
    found = {read_visit(browser, visit_id).json()["state"]}
    for listed in (period(browser, DAY), period(browser, DAY, "2026-12-06"), all_visits(browser)):
        found |= {item["state"] for item in items(listed) if item["id"] == visit_id}
    return found


@pytest.fixture
def scene(crm: Crm) -> tuple[FakeClock, Browser, Browser, str]:
    visits_clock = FakeClock(datetime(2026, 11, 30, 8, 0, tzinfo=UTC))
    crm.app.state.clock = visits_clock
    rep_a, manager = crm.login(REP_A, ["rep"]), crm.login(MANAGER, ["manager"])
    created = planned(rep_a, visit_body(customer(rep_a, "Gospodarstwo K05"), (DAY, "10:00"),
                                        (DAY, "11:00")))  # fmt: skip
    assert created["state"] == "planned"
    return visits_clock, rep_a, manager, created["id"]


def test_k05_planned_until_the_end_instant_and_held_from_it(
    crm: Crm, scene: tuple[FakeClock, Browser, Browser, str]
) -> None:
    visits_clock, rep_a, manager, visit_id = scene
    stored = raw_visit_row(crm.pg, visit_id)
    visits_clock.at = ENDS_AT.replace(hour=9, minute=59, second=59)
    assert states(rep_a, visit_id) == {"planned"}
    assert states(manager, visit_id) == {"planned"}
    # Contrast: only the clock moves, by one second, with no write in between.
    visits_clock.at = ENDS_AT
    assert states(rep_a, visit_id) == {"held"}
    assert states(manager, visit_id) == {"held"}
    assert raw_visit_row(crm.pg, visit_id) == stored


def test_k05_edge_a_visit_in_progress_is_planned(
    scene: tuple[FakeClock, Browser, Browser, str],
) -> None:
    visits_clock, rep_a, _, visit_id = scene
    visits_clock.at = ENDS_AT.replace(hour=9, minute=30)
    assert states(rep_a, visit_id) == {"planned"}


def test_k05_edge_a_visit_planned_after_its_end_is_held_in_the_create_answer(
    crm: Crm, scene: tuple[FakeClock, Browser, Browser, str]
) -> None:
    visits_clock, rep_a, _, _ = scene
    visits_clock.at = datetime(2026, 12, 2, 12, 0, tzinfo=UTC)
    later = customer(rep_a, "Gospodarstwo K05 po")
    created = planned(rep_a, visit_body(later, ("2026-12-01", "10:00"), ("2026-12-01", "11:00")))
    assert created["state"] == "held"
    assert "moved" not in created


def test_k05_edge_a_new_visit_answers_exactly_the_documented_fields(
    scene: tuple[FakeClock, Browser, Browser, str],
) -> None:
    _, rep_a, _, visit_id = scene
    shown = read_visit(rep_a, visit_id).json()
    assert sorted(shown) == ["customer", "ends_at", "id", "own_address", "starts_at", "state"]


def test_k05_no_column_of_the_visit_table_holds_a_state(crm: Crm) -> None:
    columns = [
        name
        for (name,) in crm.pg.rows(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'visit' ORDER BY ordinal_position"
        )
    ]
    assert columns, "no visit table: the check would pass vacuously"
    assert tuple(columns) == VISIT_COLUMNS
    assert [c for c in columns if any(w in c for w in ("state", "status", "held", "planned"))] == []
