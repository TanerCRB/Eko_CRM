"""EKO-3-08 K-04 (ADR-0003-C5/C6, *Roles*; ADR-0003-C37 in the accepted addendum draft, "the copy
is never an authority"): the session read exposes the caller's application roles from the token
verified for that request, and a copy rewritten in the database changes no answer for its
subject; the same rewrites do change the manager's reps list, so the tamper reached the store.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, created_id, listed_ids
from tests.runtime.eko308.conftest import (
    A1,
    M2,
    R1,
    REPS,
    SESSION,
    Staff,
    Z,
    rep_subjects,
    session_view,
)
from tests.support import oidc_stub

pytestmark = pytest.mark.runtime

REFUSED = (403, {"detail": "not permitted"})


def roles_of(view: dict[str, Any]) -> set[str]:
    roles: list[str] = view["roles"]
    assert len(roles) == len(set(roles)), roles
    return set(roles)


@pytest.mark.parametrize(
    ("roles", "shown"),
    [
        pytest.param(["rep"], {"rep"}, id="rep"),
        pytest.param(["rep", "manager"], {"rep", "manager"}, id="rep-and-manager"),
        pytest.param(["administrator"], {"administrator"}, id="administrator-only"),
        pytest.param(["manager"], {"manager"}, id="manager-only"),
    ],
)
def test_k04_the_session_read_shows_the_tokens_application_roles(
    staff: Staff, roles: list[str], shown: set[str]
) -> None:
    view = session_view(staff.login(R1, roles, "Anna Testowa"))
    assert set(view) == {"subject", "name", "roles"}
    assert (view["subject"], view["name"]) == (R1, "Anna Testowa")
    assert roles_of(view) == shown


def test_k04_realm_roles_other_clients_and_unknown_names_are_not_shown(staff: Staff) -> None:
    claims = {
        "realm_access": {"roles": ["manager", "administrator"]},
        "resource_access": {
            oidc_stub.CLIENT_ID: {"roles": ["rep", "rep", "auditor", "Manager"]},
            "account": {"roles": ["manager"]},
        },
    }
    view = session_view(staff.login(R1, ["rep"], "Anna Testowa", **claims))
    assert view["roles"] == ["rep"]


def test_k04_roles_follow_the_refreshed_token_without_a_new_login(staff: Staff) -> None:
    browser = staff.login(R1, ["rep", "manager"], "Anna Testowa")
    assert roles_of(session_view(browser)) == {"rep", "manager"}
    assert browser.send("GET", REPS).status_code == 200
    for session in staff.stub.sessions.values():
        session.user.client_roles = ["rep"]
    staff.clock.advance(seconds=staff.stub.access_lifespan_seconds + 1)
    assert roles_of(session_view(browser)) == {"rep"}
    refused = browser.send("GET", REPS)
    assert (refused.status_code, refused.json()) == REFUSED


def test_k04_a_rewritten_copy_changes_no_answer_for_its_subject(staff: Staff) -> None:
    administrator = staff.login(A1, ["administrator"], "Adam Administracyjny")
    rep = staff.login(R1, ["rep"], "Anna Testowa")
    staff.stub.access_overrides = {"resource_access": None}
    staff.stub.next_user = oidc_stub.User(sub=Z, client_roles=[])
    nobody = staff.crm.open_browser(staff.app)
    nobody.login()
    assert nobody.session is not None
    manager = staff.login(M2, ["manager"], "Maria Kierownicza")
    owned = {created_id(rep, {"name": "Ferma K04"})}
    assert rep_subjects(manager) == {R1}

    with staff.pg.connect() as connection:
        connection.execute("UPDATE staff_display_name SET is_rep = true WHERE subject = %s", (A1,))
        connection.execute("UPDATE staff_display_name SET is_rep = false WHERE subject = %s", (R1,))
        connection.execute(
            "INSERT INTO staff_display_name (subject, display_name, is_rep, last_login_at) "
            "VALUES (%s, 'Zenon Wstawiony', true, now()) "
            "ON CONFLICT (subject) DO UPDATE SET is_rep = true",
            (Z,),
        )

    # Contrast: the tamper reached the store the list reads.
    assert rep_subjects(manager) == {A1, Z}
    # No answer for the tampered subjects changed.
    refused = administrator.send("GET", CUSTOMERS)
    assert (refused.status_code, refused.json()) == REFUSED
    assert roles_of(session_view(administrator)) == {"administrator"}
    assert roles_of(session_view(rep)) == {"rep"}
    assert listed_ids(rep) == owned
    for path in (CUSTOMERS, SESSION, REPS):
        answered = nobody.send("GET", path)
        assert (answered.status_code, answered.json()) == REFUSED, path


def test_k04_edge_a_role_less_session_gets_403_on_the_session_read(staff: Staff) -> None:
    staff.stub.access_overrides = {"resource_access": None}
    staff.stub.next_user = oidc_stub.User(sub=Z, client_roles=[])
    browser = staff.crm.open_browser(staff.app)
    browser.login()
    answered = browser.send("GET", SESSION)
    assert (answered.status_code, answered.json()) == REFUSED
    assert "roles" not in answered.text
