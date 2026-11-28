"""EKO-3-08 K-05 (ADR-0005 *Retention*, G-8 A, ADR-0005-C9 in part and C20's behavioural half;
ADR-0003-C7; the accepted addendum draft: the reference set is `customer.owner_subject`, the bound
is 180 x 24 h after the last login between UTC instants, inclusive). The worker's retention run,
`retention.run_once`, is the only remover of a copy: an unreferenced copy is gone by the bound, a
referenced one is kept, and a deactivated account changes neither its copy nor its customers.
"""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest

from tests.runtime.eko201.conftest import refused_at_callback
from tests.runtime.eko301.conftest import created_id, stored_counts
from tests.runtime.eko308.conftest import (
    R1,
    R2,
    SESSION,
    Staff,
    copies,
    raw_copy_rows,
    run_retention,
)

pytestmark = pytest.mark.runtime

DAY = timedelta(hours=24)
BOUND = 180 * DAY
MAX_WAIT_SECONDS = 60.0
UNREFERENCED = R1
OWNER = R2


def customer_rows(staff: Staff) -> list[tuple[object, ...]]:
    return staff.pg.rows("SELECT to_jsonb(c)::text FROM customer c ORDER BY id")


def own_a_customer(staff: Staff, subject: str) -> None:
    created_id(staff.login(subject, ["rep"], "Olga Testowa"), {"name": "Ferma K05"})


def own_a_visit(staff: Staff, subject: str) -> None:
    """A visit `subject` owns, on a customer a subject with no copy owns: only the visit refers to
    `subject` (EKO-4-01, ADR-0005-C21 for `visit.owner_subject`). Planted through SQL, since no
    operation plans a visit on another owner's customer."""
    staff.login(subject, ["rep"], "Olga Testowa")
    customer_id, visit_id = str(uuid.uuid4()), str(uuid.uuid4())
    staff.pg.rows(
        "INSERT INTO customer (id, name, country, owner_subject) "
        "VALUES (%s, 'Ferma K05 wizyta', 'PL', %s) RETURNING id",
        (customer_id, NO_COPY),
    )
    staff.pg.rows(
        "INSERT INTO visit (id, customer_id, owner_subject, starts_at, ends_at) "
        "VALUES (%s, %s, %s, '2026-11-30T09:00:00Z', '2026-11-30T10:00:00Z') RETURNING id",
        (visit_id, customer_id, subject),
    )


# A subject that never logs in, so it holds no copy.
NO_COPY = "5a1e0308-0000-4000-8000-0000000000e1"

# Each column of the reference set and how a test makes a record that refers to a subject there.
REFERRING: dict[str, Callable[[Staff, str], None]] = {
    "customer.owner_subject": own_a_customer,
    "visit.owner_subject": own_a_visit,
}


def test_k05_the_planters_cover_the_code_reference_set() -> None:
    from app.data.staff import REFERENCE_SET

    assert {f"{c.table.name}.{c.name}" for c in REFERENCE_SET} == set(REFERRING)


def test_k05_an_unreferenced_copy_is_gone_by_180_days_after_the_last_login(
    staff: Staff, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = staff.clock.now()
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    staff.clock.at = t + 179 * DAY
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED in copies(staff.pg)
    staff.clock.at = t + BOUND - timedelta(microseconds=1)
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED in copies(staff.pg)
    staff.clock.at = t + BOUND
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED not in copies(staff.pg)


def test_k05_an_unreferenced_copy_is_gone_one_day_after_the_bound(
    staff: Staff, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = staff.clock.now()
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    staff.clock.at = t + 181 * DAY
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert copies(staff.pg) == {}


@pytest.mark.parametrize("column", sorted(REFERRING))
def test_k05_a_referenced_copy_is_kept_past_the_bound(
    staff: Staff, monkeypatch: pytest.MonkeyPatch, column: str
) -> None:
    t = staff.clock.now()
    REFERRING[column](staff, OWNER)
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    staff.clock.at = t + 181 * DAY
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert set(copies(staff.pg)) == {OWNER}


def test_k05_contrast_a_new_login_moves_the_bound(
    staff: Staff, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = staff.clock.now()
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    staff.clock.at = t + 100 * DAY
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    staff.clock.at = t + 181 * DAY
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED in copies(staff.pg)
    staff.clock.at = t + 280 * DAY
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED not in copies(staff.pg)


def test_k05_edge_a_new_login_after_deletion_stores_the_copy_again(
    staff: Staff, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = staff.clock.now()
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    staff.clock.at = t + BOUND
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED not in copies(staff.pg)
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    assert copies(staff.pg)[UNREFERENCED].last_login_at == t + BOUND


def test_k05_the_worker_wakes_by_the_next_copy_bound(
    staff: Staff, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = staff.clock.now()
    staff.login(UNREFERENCED, ["rep"], "Urszula Testowa")
    # Past every session and transaction bound, 30 s before the copy's.
    staff.clock.at = t + BOUND - timedelta(seconds=30)
    wait = run_retention(staff.pg, staff.clock, monkeypatch)
    assert stored_counts(staff.pg)["customer"] == 0
    assert staff.pg.rows("SELECT count(*) FROM app_session") == [(0,)]
    assert wait == pytest.approx(30.0)
    staff.clock.at = t + BOUND
    run_retention(staff.pg, staff.clock, monkeypatch)
    assert UNREFERENCED not in copies(staff.pg)


def test_k05_edge_a_kept_copy_past_its_bound_does_not_make_the_worker_spin(
    staff: Staff, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = staff.clock.now()
    own_a_customer(staff, OWNER)
    staff.clock.at = t + 181 * DAY
    assert run_retention(staff.pg, staff.clock, monkeypatch) == MAX_WAIT_SECONDS
    assert set(copies(staff.pg)) == {OWNER}


def test_k05_a_refused_refresh_changes_neither_the_copy_nor_the_customers(staff: Staff) -> None:
    browser = staff.login(OWNER, ["rep"], "Olga Testowa")
    created_id(browser, {"name": "Ferma K05"})
    copy_before, customers_before = raw_copy_rows(staff.pg), customer_rows(staff)
    staff.stub.refresh_mode = "refuse"
    staff.clock.advance(seconds=staff.stub.access_lifespan_seconds + 1)
    assert browser.send("GET", SESSION).status_code == 401
    assert staff.pg.rows("SELECT count(*) FROM app_session WHERE subject = %s", (OWNER,)) == [(0,)]
    assert raw_copy_rows(staff.pg) == copy_before
    assert customer_rows(staff) == customers_before


def test_k05_a_refused_next_login_changes_neither_the_copy_nor_the_customers(
    staff: Staff,
) -> None:
    own_a_customer(staff, OWNER)
    copy_before, customers_before = raw_copy_rows(staff.pg), customer_rows(staff)
    staff.stub.code_mode = "refuse"
    staff.clock.advance(hours=1)
    staff.stub.access_overrides = {"name": "Olga Zmieniona"}
    browser = staff.crm.open_browser(staff.app)
    assert refused_at_callback(browser.login())
    assert raw_copy_rows(staff.pg) == copy_before
    assert customer_rows(staff) == customers_before
    # Contrast: the same account, not deactivated, logging in with a changed name changes it.
    staff.stub.code_mode = "answer"
    staff.login(OWNER, ["rep"], "Olga Zmieniona")
    assert raw_copy_rows(staff.pg) != copy_before
    assert copies(staff.pg)[OWNER].display_name == "Olga Zmieniona"
