"""EKO-4-01 K-02 (ACC-4, PRH-4, ACC-8; the accepted addendum's ADR-0003-C42): a rep reads only the
visits it owns, by the visit's own owner and never its customer's; the manager reads every visit.

Today the two owners always coincide, so one visit owned by A on a customer owned by someone else
is planted through SQL: only that row tells the visit-owner predicate from a customer-owner one.
Another rep's visit by identifier is answered exactly as an identifier that exists nowhere.
Runtime, on real PostgreSQL and the OIDC stub; every value is synthetic.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, ROLE_LESS, Crm
from tests.runtime.eko401.conftest import (
    ELSEWHERE,
    EMPTY,
    NOT_FOUND,
    NOT_PERMITTED,
    PERIOD,
    VISITS,
    all_visits,
    answer,
    customer,
    ids,
    period,
    plan,
    planned_id,
    plant_customer,
    plant_visit,
    read_visit,
    status_and_json,
    visit_body,
    visit_url,
)

pytestmark = pytest.mark.runtime

DAY = "2026-11-30"
WEEK = ("2026-11-30", "2026-12-06")
OTHER_DAY = "2026-12-01"


def own_visits(crm: Crm) -> tuple[list[str], list[str]]:
    """Two visits of A and two of B, all on `DAY`."""
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    a, b = customer(rep_a, "Gospodarstwo A"), customer(rep_b, "Gospodarstwo B")
    of_a = [
        planned_id(rep_a, visit_body(a, (DAY, "08:00"), (DAY, "09:00"))),
        planned_id(rep_a, visit_body(a, (DAY, "12:00"), (DAY, "13:00"))),
    ]
    of_b = [
        planned_id(rep_b, visit_body(b, (DAY, "09:00"), (DAY, "10:00"))),
        planned_id(rep_b, visit_body(b, (DAY, "14:00"), (DAY, "15:00"))),
    ]
    return of_a, of_b


def test_k02_a_rep_lists_and_reads_only_its_own_visits(crm: Crm) -> None:
    of_a, of_b = own_visits(crm)
    rep_a = crm.login(REP_A, ["rep"])
    assert ids(period(rep_a, DAY)) == of_a
    assert ids(period(rep_a, *WEEK)) == of_a
    assert ids(all_visits(rep_a)) == of_a
    for visit_id in of_a:
        assert read_visit(rep_a, visit_id).status_code == 200


def test_k02_another_reps_visit_by_id_is_indistinguishable_from_a_missing_one(crm: Crm) -> None:
    of_a, _ = own_visits(crm)
    rep_b = crm.login(REP_B, ["rep"])
    foreign = read_visit(rep_b, of_a[0])
    nowhere = read_visit(rep_b, str(uuid.uuid4()))
    assert answer(foreign) == answer(nowhere)
    assert status_and_json(foreign) == NOT_FOUND
    # Contrast: the same read, changing only the caller to A, returns the full visit.
    rep_a = crm.login(REP_A, ["rep"])
    found = read_visit(rep_a, of_a[0])
    assert found.status_code == 200
    assert found.json()["id"] == of_a[0]


@pytest.mark.parametrize("roles", [["manager"], ["rep", "manager"]], ids=["manager", "both"])
def test_k02_the_manager_reads_every_visit(crm: Crm, roles: list[str]) -> None:
    of_a, of_b = own_visits(crm)
    manager = crm.login(MANAGER if roles == ["manager"] else REP_AND_MANAGER, roles)
    every = sorted(of_a + of_b)
    assert sorted(ids(period(manager, DAY))) == every
    assert sorted(ids(period(manager, *WEEK))) == every
    assert sorted(ids(all_visits(manager))) == every
    for visit_id in every:
        assert read_visit(manager, visit_id).status_code == 200


def test_k02_visibility_follows_the_visits_owner_not_its_customers(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    elsewhere = plant_customer(crm.pg, ELSEWHERE, "Gospodarstwo Gdzie Indziej")
    starts = datetime(2026, 11, 30, 9, 0, tzinfo=UTC)
    planted = plant_visit(crm.pg, REP_A, elsewhere, starts, starts.replace(hour=10))
    assert ids(period(rep_a, DAY)) == [planted]
    assert ids(all_visits(rep_a)) == [planted]
    shown = read_visit(rep_a, planted)
    assert shown.status_code == 200
    # A-3 A: the customer values a visit carries are read under the visit's scope.
    assert shown.json()["customer"]["name"] == "Gospodarstwo Gdzie Indziej"
    assert items_of(period(rep_b, DAY)) == EMPTY
    assert items_of(all_visits(rep_b)) == EMPTY
    assert answer(read_visit(rep_b, planted)) == answer(read_visit(rep_b, str(uuid.uuid4())))


def items_of(response: httpx.Response) -> Any:
    status, body = status_and_json(response)
    assert status == 200, body
    return body


def test_k02_edge_a_rep_with_no_visits_gets_empty_lists_with_no_trace_of_others(
    crm: Crm,
) -> None:
    own_visits(crm)
    rep_c = crm.login("5a1e0401-0000-4000-8000-0000000000c3", ["rep"])
    busy, quiet = period(rep_c, DAY), period(rep_c, "2027-01-15")
    assert status_and_json(busy) == (200, EMPTY)
    assert answer(busy) == answer(quiet)
    assert status_and_json(all_visits(rep_c)) == (200, EMPTY)
    assert answer(period(rep_c, *WEEK)) == answer(period(rep_c, "2027-01-11", "2027-01-17"))


def test_k02_edge_every_visit_answer_carries_no_store(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo A")
    created = plan(rep_a, visit_body(own))
    visit_id = created.json()["id"]
    responses = {
        "created": created,
        "read": read_visit(rep_a, visit_id),
        "period": period(rep_a, DAY),
        "all": all_visits(rep_a),
        "missing": read_visit(rep_a, str(uuid.uuid4())),
        "not-uuid": rep_a.send("GET", f"{VISITS}/not-a-uuid"),
        "bad-period": rep_a.send("GET", PERIOD, params={"first": "2026-02-30", "last": DAY}),
        "rejected": plan(rep_a, {"customer_id": own}),
        "no-session": crm.open_browser(crm.app).send("GET", visit_url(visit_id)),
        "role-less": read_visit(crm.login(ROLE_LESS, []), visit_id),
    }
    assert {k: r.headers.get("cache-control") for k, r in responses.items()} == dict.fromkeys(
        responses, "no-store"
    )


def test_k02_edge_the_path_parameter_is_a_uuid(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    response = rep_a.send("GET", f"{VISITS}/12345")
    assert response.status_code == 422, response.text
    assert [e["loc"] for e in response.json()["detail"]] == [["path", "visit_id"]]
    document = crm.app.openapi()
    parameter = document["paths"]["/api/visits/{visit_id}"]["get"]["parameters"][0]
    assert parameter["schema"]["format"] == "uuid"


def test_k02_edge_role_less_and_no_session_are_refused_on_reads(crm: Crm) -> None:
    role_less = crm.login(ROLE_LESS, [])
    assert status_and_json(all_visits(role_less)) == NOT_PERMITTED
    assert status_and_json(period(role_less, DAY)) == NOT_PERMITTED
    anonymous = crm.open_browser(crm.app)
    assert anonymous.send("GET", VISITS).status_code == 401
    assert period(anonymous, OTHER_DAY).status_code == 401
