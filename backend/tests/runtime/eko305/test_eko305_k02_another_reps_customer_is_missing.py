"""EKO-3-05 K-02 (ACC-4, ACC-8, PRH-4; ADR-0003-C33 by-id clause; ADR-0003-C41): a rep's edit,
archive or restore of another rep's customer answers exactly as the same call on a well-formed
identifier that exists nowhere (status, body, and headers other than `Eko-Correlation-Id`), and
leaves that customer's row and contacts byte-identical, `archived_at` included.

The scenario reaches the ownership predicate: the target is an existing customer of rep B, the
edit carries a valid body, and the stored rows are compared directly, so a 404 from another
mechanism (a 422 judged first, a 401, a scoped pre-read before an unscoped write) cannot pass.
The same holds for rep B's customer once archived: no state-dependent answer reaches rep A.
"""

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import ORIGIN, Browser, FakeClock
from tests.runtime.eko301.conftest import (
    ADMINISTRATOR,
    MANAGER,
    REP_A,
    REP_AND_MANAGER,
    REP_B,
    ROLE_LESS,
    Crm,
    customer_url,
)
from tests.runtime.eko305.conftest import (
    NOT_FOUND,
    NOT_PERMITTED,
    answer,
    archive,
    archived_at,
    customer,
    edit,
    email,
    phone,
    read,
    restore,
    snapshot,
    status_and_json,
)
from tests.support import eko302_nip as nips
from tests.support.api_surface import route_contexts
from tests.support.c2_routes import body_routes

pytestmark = pytest.mark.runtime

SECRET_NAME = "Gospodarstwo Tajne K02"
SECRET_PHONE = "+48601305202"
SECRET_EMAIL = "tajne-k02@farm.example.invalid"
SECRET_NOTE = "Tylko dla przedstawiciela B"
B_CUSTOMER: dict[str, Any] = {
    "name": SECRET_NAME,
    "town": "Tajna Wola",
    "contacts": [
        phone(SECRET_PHONE, SECRET_NOTE, primary=True),
        email(SECRET_EMAIL, "Druga notatka K02"),
    ],
}
VALID_EDIT: dict[str, Any] = {
    "name": "Gospodarstwo Przejete K02",
    "contacts": [phone("+48601305299", primary=True)],
}
Operation = Callable[[Browser, str], httpx.Response]
OPERATIONS: dict[str, Operation] = {
    "edit": lambda browser, customer_id: edit(browser, customer_id, VALID_EDIT),
    "archive": archive,
    "restore": restore,
}
PATHS = {
    ("PUT", "/api/customers/{customer_id}"),
    ("POST", "/api/customers/{customer_id}/archive"),
    ("POST", "/api/customers/{customer_id}/restore"),
}


def nowhere(crm: Crm) -> str:
    identifier = str(uuid.uuid4())
    assert crm.pg.rows("SELECT count(*) FROM customer WHERE id = %s", (identifier,)) == [(0,)]
    return identifier


def b_rows(crm: Crm, customer_id: str) -> tuple[Any, ...]:
    rows, contacts = snapshot(crm)
    return rows[customer_id], contacts.get(customer_id, [])


@pytest.fixture
def b_customer(crm: Crm) -> str:
    return customer(crm.login(REP_B, ["rep"]), **B_CUSTOMER)


def assert_answered_as_missing(
    crm: Crm, rep_a: Browser, target: str, operation: str, manager: Browser
) -> None:
    before_rows = b_rows(crm, target)
    before_read = read(manager, target).content
    denied = OPERATIONS[operation](rep_a, target)
    missing = OPERATIONS[operation](rep_a, nowhere(crm))
    assert status_and_json(denied) == NOT_FOUND, (operation, denied.text)
    assert answer(denied) == answer(missing), operation
    for value in (SECRET_NAME, SECRET_PHONE, SECRET_EMAIL, SECRET_NOTE, target, REP_B):
        assert value.encode() not in denied.content, (operation, value)
        assert all(value not in v for _, v in denied.headers.multi_items()), (operation, value)
    assert b_rows(crm, target) == before_rows, operation
    assert read(manager, target).content == before_read, operation


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_k02_a_reps_change_of_another_reps_active_customer_is_answered_as_missing(
    crm: Crm, b_customer: str, operation: str
) -> None:
    rep_a, manager = crm.login(REP_A, ["rep"]), crm.login(MANAGER, ["manager"])
    assert archived_at(crm, b_customer) is None
    assert_answered_as_missing(crm, rep_a, b_customer, operation, manager)


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_k02_a_reps_change_of_another_reps_archived_customer_is_answered_as_missing(
    crm: Crm, b_customer: str, clock: FakeClock, operation: str
) -> None:
    rep_b = crm.login(REP_B, ["rep"])
    assert archive(rep_b, b_customer).status_code == 200
    assert archived_at(crm, b_customer) == clock.now()
    clock.advance(seconds=5)
    rep_a, manager = crm.login(REP_A, ["rep"]), crm.login(MANAGER, ["manager"])
    assert_answered_as_missing(crm, rep_a, b_customer, operation, manager)


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(MANAGER, ["manager"], id="manager"),
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
    ],
)
def test_k02_contrast_the_manager_changes_the_same_active_customer(
    crm: Crm, b_customer: str, clock: FakeClock, subject: str, roles: list[str]
) -> None:
    manager = crm.login(subject, roles)
    before = b_rows(crm, b_customer)
    edited = edit(manager, b_customer, VALID_EDIT)
    assert edited.status_code == 200, edited.text
    assert b_rows(crm, b_customer) != before
    archived = archive(manager, b_customer)
    assert (archived.status_code, archived.json()["archived"]) == (200, True)
    assert archived_at(crm, b_customer) == clock.now()
    restored = restore(manager, b_customer)
    assert (restored.status_code, restored.json()["archived"]) == (200, False)
    assert archived_at(crm, b_customer) is None


def test_k02_contrast_the_manager_restores_the_same_archived_customer(
    crm: Crm, b_customer: str
) -> None:
    rep_b = crm.login(REP_B, ["rep"])
    assert archive(rep_b, b_customer).status_code == 200
    manager = crm.login(MANAGER, ["manager"])
    # A repeat archive is a success inside the scope: the state answer the rep never gets.
    repeat = archive(manager, b_customer)
    assert (repeat.status_code, repeat.json()["archived"]) == (200, True)
    restored = restore(manager, b_customer)
    assert (restored.status_code, restored.json()["archived"]) == (200, False)
    assert archived_at(crm, b_customer) is None


@pytest.mark.parametrize("malformed", ["not-a-uuid", "12345"])
@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_k02_a_non_uuid_identifier_gets_the_same_422_for_a_rep_and_the_manager(
    crm: Crm, b_customer: str, operation: str, malformed: str
) -> None:
    rep_a, manager = crm.login(REP_A, ["rep"]), crm.login(MANAGER, ["manager"])
    before = snapshot(crm)
    for_rep = OPERATIONS[operation](rep_a, malformed)
    for_manager = OPERATIONS[operation](manager, malformed)
    assert for_rep.status_code == 422, for_rep.text
    assert answer(for_rep) == answer(for_manager)
    assert snapshot(crm) == before


INVALID_EDITS: dict[str, dict[str, Any]] = {
    "empty-name": {"name": ""},
    "no-name": {},
    "bad-postal-code": {"name": "Gospodarstwo", "postal_code": "00000"},
    "two-primaries": {
        "name": "Gospodarstwo",
        "contacts": [phone("+48601305281", primary=True), phone("+48601305282", primary=True)],
    },
}


@pytest.mark.parametrize("variant", sorted(INVALID_EDITS))
def test_k02_an_invalid_edit_to_another_reps_customer_equals_the_one_to_a_missing_id(
    crm: Crm, b_customer: str, variant: str
) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    before = snapshot(crm)
    denied = edit(rep_a, b_customer, INVALID_EDITS[variant])
    missing = edit(rep_a, nowhere(crm), INVALID_EDITS[variant])
    assert denied.status_code == 422, denied.text
    assert answer(denied) == answer(missing)
    assert snapshot(crm) == before


def send(browser: Browser, method: str, path: str, origin: str | None, **kwargs: Any) -> Any:
    return status_and_json(browser.send(method, path, origin=origin, **kwargs))


def test_k02_a_refused_caller_gets_the_access_answer_whatever_the_body_and_nothing_changes(
    crm: Crm, b_customer: str
) -> None:
    callers: dict[str, tuple[Browser, str | None, Any]] = {
        "no-session": (crm.open_browser(crm.app), ORIGIN, (401, {"detail": "not authenticated"})),
        "foreign-origin": (
            crm.login(REP_B, ["rep"]),
            "https://elsewhere.test",
            (403, {"detail": "origin refused"}),
        ),
        "administrator-only": (crm.login(ADMINISTRATOR, ["administrator"]), ORIGIN, NOT_PERMITTED),
        "role-less": (crm.login(ROLE_LESS, []), ORIGIN, NOT_PERMITTED),
    }
    bodies: dict[str, dict[str, Any]] = {
        "valid": {"json": VALID_EDIT},
        "invalid": {"json": {"name": "", "contacts": [{"kind": "fax", "value": ""}]}},
        "not-json": {"content": b'{"name": "x', "headers": {"content-type": "application/json"}},
        "none": {},
    }
    requests = [
        ("PUT", customer_url(b_customer)),
        ("POST", f"{customer_url(b_customer)}/archive"),
        ("POST", f"{customer_url(b_customer)}/restore"),
    ]
    before = snapshot(crm)
    for label, (browser, origin, expected) in callers.items():
        for method, path in requests:
            for variant, kwargs in bodies.items():
                got = send(browser, method, path, origin, **kwargs)
                assert got == expected, (label, method, path, variant, got)
    assert snapshot(crm) == before


def test_k02_the_three_operations_are_served_and_the_edit_is_a_body_route(crm: Crm) -> None:
    """The C34 body-route walk and the C5 role-gate walk read the route table as served; the new
    operations must be in it for those walks to reach them (row 47)."""
    served = {
        (method, context.path or "")
        for context in route_contexts(crm.app)
        for method in getattr(context.route, "methods", None) or ()
    }
    assert served >= PATHS
    assert ("PUT", "/api/customers/{customer_id}") in {
        (r.method, r.path) for r in body_routes(crm.app)
    }


def test_k02_contrast_the_managers_edit_of_the_archived_customer_is_refused_409(
    crm: Crm, b_customer: str
) -> None:
    assert archive(crm.login(REP_B, ["rep"]), b_customer).status_code == 200
    manager = crm.login(MANAGER, ["manager"])
    before = b_rows(crm, b_customer)
    refused = edit(manager, b_customer, VALID_EDIT)
    assert status_and_json(refused) == (409, {"detail": "restore it first"})
    assert b_rows(crm, b_customer) == before
    # The rep's same call on the same archived customer is the missing-id 404 (scope first).
    rep_a = crm.login(REP_A, ["rep"])
    assert answer(edit(rep_a, b_customer, VALID_EDIT)) == answer(
        edit(rep_a, nowhere(crm), VALID_EDIT)
    )


TAKEN = nips.valid_nip(305281)
TAKEN_BY_B = nips.valid_nip(305291)


@pytest.mark.parametrize("held_by", ["the-reps-own", "another-of-rep-bs"])
@pytest.mark.parametrize("target_archived", [False, True], ids=["active", "archived"])
def test_k02_a_taken_nip_gives_no_answer_outside_the_scope(
    crm: Crm, b_customer: str, held_by: str, target_archived: bool
) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    customer(rep_a, "Gospodarstwo A NIP K02", tax_id=TAKEN)
    customer(rep_b, "Gospodarstwo B NIP K02", tax_id=TAKEN_BY_B)
    if target_archived:
        assert archive(rep_b, b_customer).status_code == 200
    nip = TAKEN if held_by == "the-reps-own" else TAKEN_BY_B
    body = {**VALID_EDIT, "tax_id": nip}
    before = snapshot(crm)
    denied = edit(rep_a, b_customer, body)
    missing = edit(rep_a, nowhere(crm), body)
    assert status_and_json(denied) == NOT_FOUND, denied.text
    assert answer(denied) == answer(missing)
    assert b"existing_customer_id" not in denied.content
    assert snapshot(crm) == before


def test_k02_contrast_the_managers_same_edit_meets_the_nip_with_the_holder(
    crm: Crm, b_customer: str
) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    holder = customer(rep_a, "Gospodarstwo A NIP K02", tax_id=TAKEN)
    manager = crm.login(MANAGER, ["manager"])
    before = snapshot(crm)
    taken = edit(manager, b_customer, {**VALID_EDIT, "tax_id": TAKEN})
    assert status_and_json(taken) == (
        409,
        {
            "detail": "a customer with this NIP already exists - contact your manager",
            "existing_customer_id": holder,
        },
    )
    assert snapshot(crm) == before
