"""EKO-3-08 K-03 (ACC-4, PRH-4, ACC-8; ADR-0003-C5, C6): anyone without `manager` calling the
reps list gets the role refusal, 403 `{"detail":"not permitted"}`, byte-equal however many reps
are stored and whatever the caller names in a header, a query, a body or a cookie; a manager gets
the list. The route's own manager check is the only guard for a rep, since the app-wide gate
admits a rep to every CRM-class route.
"""

from typing import Any

import pytest

from tests.runtime.eko201.conftest import Browser
from tests.runtime.eko308.conftest import (
    A1,
    M1,
    M2,
    R1,
    R2,
    REPS,
    Staff,
    answer,
    rep_subjects,
)
from tests.support import oidc_stub

pytestmark = pytest.mark.runtime

REFUSAL = b'{"detail":"not permitted"}'
OTHER_REPS = [f"5a1e0308-0000-4000-8000-0000000001{n:02d}" for n in range(5)]


def wipe_copies(staff: Staff) -> None:
    with staff.pg.connect() as connection:
        connection.execute("TRUNCATE staff_display_name")


def refused(response: Any) -> Any:
    assert response.status_code == 403, response.text[:300]
    assert response.content == REFUSAL
    return answer(response)


def test_k03_a_reps_refusal_is_byte_equal_whatever_is_stored_or_named(staff: Staff) -> None:
    rep = staff.login(R1, ["rep"], "Anna Testowa")
    with_itself = refused(rep.send("GET", REPS))
    wipe_copies(staff)
    nothing = refused(rep.send("GET", REPS))
    for subject in OTHER_REPS:
        staff.login(subject, ["rep"], "Robert Testowy")
    five = refused(rep.send("GET", REPS))
    named = [
        rep.send("GET", REPS, headers={"x-eko-role": "manager", "x-roles": "manager"}),
        rep.send("GET", REPS, params={"role": "manager", "roles": "manager"}),
        rep.send("GET", REPS, json={"roles": ["manager"]}),
    ]
    rep.jar["roles"] = "manager"
    named.append(rep.send("GET", REPS))
    rep.jar.pop("roles")
    for other in (nothing, five, *(refused(r) for r in named)):
        assert other == with_itself


@pytest.mark.parametrize(
    ("subject", "claims"),
    [
        pytest.param(A1, {}, id="administrator-only"),
        pytest.param(R2, {"resource_access": None}, id="role-less"),
    ],
)
def test_k03_administrator_only_and_role_less_get_the_same_refusal(
    staff: Staff, subject: str, claims: dict[str, Any]
) -> None:
    rep = staff.login(R1, ["rep"], "Anna Testowa")
    expected = refused(rep.send("GET", REPS))
    staff.stub.access_overrides = {"name": "Adam Testowy", **claims}
    staff.stub.next_user = oidc_stub.User(sub=subject, client_roles=["administrator"])
    other: Browser = staff.crm.open_browser(staff.app)
    other.login()
    assert other.session is not None, "no session: the refusal would be a 401"
    assert refused(other.send("GET", REPS)) == expected


def test_k03_contrast_a_manager_with_the_same_stored_reps_gets_the_list(staff: Staff) -> None:
    rep = staff.login(R1, ["rep"], "Anna Testowa")
    refused(rep.send("GET", REPS))
    assert rep_subjects(staff.login(M2, ["manager"])) == {R1}


def test_k03_edge_manager_and_administrator_answers_as_manager_alone(staff: Staff) -> None:
    staff.login(R1, ["rep"], "Anna Testowa")
    alone = staff.login(M2, ["manager"], "Maria Kierownicza").send("GET", REPS)
    both = staff.login(M1, ["manager", "administrator"], "Maria Kierownicza").send("GET", REPS)
    assert alone.status_code == 200
    assert answer(both) == answer(alone)
