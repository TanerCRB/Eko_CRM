"""EKO-4-01 K-01 (ACC-7, ACC-5, ADR-0003-C35, the accepted addendum's ADR-0003-C42): a rep plans a
visit only for a customer it owns, and the visit's owner is the caller, never a request value.

Every ownership scenario uses a session holding `rep`, so the role gate is passed and a refusal can
only come from the customer lookup under the caller's own records. The manager-only scenario tests
the creation scope's role requirement. Answers come in the order of C42: access, the body alone,
the creation scope, the customer under the own-records scope, the all-records caller's 403, the
archived state. Runtime, on real PostgreSQL and the OIDC stub; every value is synthetic.
"""

import uuid
from typing import Any

import pytest

from tests.runtime.eko301.conftest import (
    ADMINISTRATOR,
    MANAGER,
    REP_A,
    REP_AND_MANAGER,
    REP_B,
    ROLE_LESS,
    Crm,
)
from tests.runtime.eko305.conftest import archive, restore
from tests.runtime.eko401.conftest import (
    NOT_FOUND,
    NOT_PERMITTED,
    PERIOD,
    RESTORE_FIRST,
    VISITS,
    answer,
    customer,
    plan,
    planned,
    read_visit,
    status_and_json,
    stored_visit,
    visit_body,
    visit_count,
    visit_url,
)

pytestmark = pytest.mark.runtime


def test_k01_a_rep_plans_a_visit_for_its_own_customer_and_owns_it(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo K01")
    created = planned(rep_a, visit_body(own))
    assert created["customer"]["id"] == own
    assert created["customer"]["name"] == "Gospodarstwo K01"
    assert uuid.UUID(created["id"]).version == 4
    by_id = read_visit(rep_a, created["id"])
    assert status_and_json(by_id) == (200, created)
    row = stored_visit(crm.pg, created["id"])
    assert (row["customer_id"], row["owner_subject"]) == (own, REP_A)
    assert visit_count(crm.pg) == 1


@pytest.mark.parametrize("field", ["owner_subject", "owner"])
def test_k01_an_owner_named_in_the_body_is_refused_as_an_unknown_field(
    crm: Crm, field: str
) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo K01")
    body = visit_body(own)
    body[field] = REP_B
    response = plan(rep_a, body)
    assert response.status_code == 422, response.text
    assert [(e["type"], e["loc"]) for e in response.json()["detail"]] == [
        ("extra_forbidden", ["body", field])
    ]
    assert REP_B not in response.text
    assert visit_count(crm.pg) == 0


def test_k01_another_reps_customer_answers_as_a_customer_that_exists_nowhere(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    own = customer(rep_a, "Gospodarstwo A")
    theirs = customer(rep_b, "Gospodarstwo B")
    foreign = plan(rep_a, visit_body(theirs))
    nowhere = plan(rep_a, visit_body(str(uuid.uuid4())))
    assert answer(foreign) == answer(nowhere)
    assert status_and_json(foreign) == NOT_FOUND
    assert visit_count(crm.pg) == 0
    # Contrast: the same request, changing only the customer to A's own.
    assert plan(rep_a, visit_body(own)).status_code == 201
    assert visit_count(crm.pg) == 1


def test_k01_a_manager_only_caller_is_refused_and_nothing_is_stored(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo A")
    manager = crm.login(MANAGER, ["manager"])
    assert status_and_json(plan(manager, visit_body(own))) == NOT_PERMITTED
    assert visit_count(crm.pg) == 0


def test_k01_contrast_a_rep_and_manager_caller_plans_for_its_own_customer(crm: Crm) -> None:
    both = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    own = customer(both, "Gospodarstwo RM")
    created = planned(both, visit_body(own))
    assert stored_visit(crm.pg, created["id"])["owner_subject"] == REP_AND_MANAGER


def test_k01_a_rep_and_manager_caller_naming_another_reps_customer_gets_403(crm: Crm) -> None:
    rep_b = crm.login(REP_B, ["rep"])
    theirs = customer(rep_b, "Gospodarstwo B")
    both = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    assert status_and_json(plan(both, visit_body(theirs))) == NOT_PERMITTED
    assert visit_count(crm.pg) == 0
    # The same caller reads that customer: the 403 is not "missing", it is "not yours to plan".
    assert both.send("GET", f"/api/customers/{theirs}").status_code == 200
    # A customer that exists nowhere is still the 404 for this caller.
    assert status_and_json(plan(both, visit_body(str(uuid.uuid4())))) == NOT_FOUND
    # Another rep's archived customer: inside its visibility scope, so the same 403.
    assert archive(rep_b, theirs).status_code == 200
    assert status_and_json(plan(both, visit_body(theirs))) == NOT_PERMITTED
    assert visit_count(crm.pg) == 0


def test_k01_edge_a_nonexistent_or_malformed_customer_id_stores_nothing(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    customer(rep_a, "Gospodarstwo A")
    assert status_and_json(plan(rep_a, visit_body(str(uuid.uuid4())))) == NOT_FOUND
    malformed = plan(rep_a, visit_body("not-a-customer-id"))
    assert malformed.status_code == 422, malformed.text
    assert [e["loc"] for e in malformed.json()["detail"]] == [["body", "customer_id"]]
    assert "not-a-customer-id" not in malformed.text
    assert visit_count(crm.pg) == 0


def test_k01_edge_an_own_archived_customer_is_refused_until_restored(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo A")
    assert archive(rep_a, own).status_code == 200
    assert status_and_json(plan(rep_a, visit_body(own))) == RESTORE_FIRST
    assert visit_count(crm.pg) == 0
    assert restore(rep_a, own).status_code == 200
    assert plan(rep_a, visit_body(own)).status_code == 201


def test_k01_edge_another_reps_archived_customer_answers_as_missing(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    theirs = customer(rep_b, "Gospodarstwo B")
    assert archive(rep_b, theirs).status_code == 200
    archived = plan(rep_a, visit_body(theirs))
    assert answer(archived) == answer(plan(rep_a, visit_body(str(uuid.uuid4()))))
    assert status_and_json(archived) == NOT_FOUND
    assert visit_count(crm.pg) == 0


def test_k01_edge_the_body_is_judged_before_the_customer_whoever_owns_it(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    own = customer(rep_a, "Gospodarstwo A")
    theirs = customer(rep_b, "Gospodarstwo B")
    backwards = {"start": ("2026-11-30", "11:00"), "end": ("2026-11-30", "10:00")}
    answers = [
        answer(plan(rep_a, visit_body(target, **backwards)))
        for target in (own, theirs, str(uuid.uuid4()))
    ]
    assert answers[0][0] == 422
    assert answers[0] == answers[1] == answers[2]
    assert visit_count(crm.pg) == 0


VALID_SHAPE: dict[str, Any] = visit_body(str(uuid.uuid4()))
INVALID_BODIES: dict[str, dict[str, Any]] = {
    "valid": {"json": VALID_SHAPE},
    "not-json": {"content": b'{"customer_id": ', "headers": {"content-type": "application/json"}},
    "fails-validation": {"json": {"customer_id": 7, "start": "now"}},
}


@pytest.mark.parametrize("refused", ["administrator-only", "role-less"])
def test_k01_edge_administrator_only_or_role_less_is_refused_before_the_body(
    crm: Crm, refused: str
) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo A")
    visit_id = planned(rep_a, visit_body(own))["id"]
    subject, roles = (
        (ADMINISTRATOR, ["administrator"]) if refused != "role-less" else (ROLE_LESS, [])
    )
    browser = crm.login(subject, roles)
    for kwargs in INVALID_BODIES.values():
        assert status_and_json(browser.send("POST", VISITS, **kwargs)) == NOT_PERMITTED
    assert status_and_json(browser.send("GET", VISITS)) == NOT_PERMITTED
    assert status_and_json(read_visit(browser, visit_id)) == NOT_PERMITTED
    listed = browser.send("GET", PERIOD, params={"first": "2026-11-30", "last": "2026-11-30"})
    assert status_and_json(listed) == NOT_PERMITTED
    assert visit_count(crm.pg) == 1


def test_k01_edge_without_a_session_every_visit_operation_answers_401(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    visit_id = planned(rep_a, visit_body(customer(rep_a, "Gospodarstwo A")))["id"]
    anonymous = crm.open_browser(crm.app)
    unauthenticated = (401, {"detail": "not authenticated"})
    assert status_and_json(anonymous.send("POST", VISITS, json=VALID_SHAPE)) == unauthenticated
    assert status_and_json(anonymous.send("GET", VISITS)) == unauthenticated
    assert status_and_json(anonymous.send("GET", visit_url(visit_id))) == unauthenticated
    listed = anonymous.send("GET", PERIOD, params={"first": "2026-11-30", "last": "2026-11-30"})
    assert status_and_json(listed) == unauthenticated
    assert visit_count(crm.pg) == 1
