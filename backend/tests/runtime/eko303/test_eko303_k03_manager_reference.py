"""EKO-3-03 K-03 (CUS-6 "the manager gets a link"; ADR-0003-C34, C38 of the gate-1 draft): a caller
holding `rep` and `manager` gets the rep's refusal plus `existing_customer_id`, which opens the
stored customer through the by-id read; a rep-only caller never gets it. Creating needs `rep`, so a
caller without it is refused 403 before any NIP is judged, whether that NIP is taken or not.
"""

import json
import uuid

import pytest

from tests.runtime.eko301.conftest import (
    ADMINISTRATOR,
    MANAGER,
    REP_A,
    REP_AND_MANAGER,
    REP_B,
    ROLE_LESS,
    Crm,
    create,
    created_id,
    customer_url,
)
from tests.runtime.eko303.conftest import (
    NIP_TAKEN,
    NOT_PERMITTED,
    UUID_FORM,
    body,
    full_body,
    headers_but,
    same_answer,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

X_NAME = "Gospodarstwo Znacznikowo-K03"


def test_k03_the_manager_gets_the_rep_refusal_plus_a_reference_that_opens_the_customer(
    crm: Crm,
) -> None:
    n = nips.valid_nip(33101)
    rep_a = crm.login(REP_A, ["rep"])
    x = created_id(rep_a, body(X_NAME, n, street="ul. Znacznikowa K03"))
    rep_b = crm.login(REP_B, ["rep"])
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    before = crm.counts()

    rep_answer = create(rep_b, full_body("Gospodarstwo K03 nowe", n, "K03"))
    manager_answer = create(manager, full_body("Gospodarstwo K03 nowe", n, "K03"))

    assert manager_answer.status_code == rep_answer.status_code == 409, manager_answer.text
    assert rep_answer.json() == NIP_TAKEN
    assert manager_answer.json() == {**NIP_TAKEN, "existing_customer_id": x}
    assert manager_answer.content == json.dumps(
        {**NIP_TAKEN, "existing_customer_id": x}, separators=(",", ":")
    ).encode("ascii")
    assert headers_but(manager_answer, "content-length") == headers_but(
        rep_answer, "content-length"
    )
    reference = manager_answer.json()["existing_customer_id"]
    assert UUID_FORM.fullmatch(reference), reference
    for needle in (n, nips.hyphenated(n), REP_A, X_NAME, "Znacznikowa"):
        assert needle not in manager_answer.text, needle
    assert crm.counts() == before

    opened = manager.send("GET", customer_url(reference))
    assert opened.status_code == 200, opened.text
    assert (opened.json()["id"], opened.json()["name"], opened.json()["tax_id"]) == (x, X_NAME, n)


def test_k03_contrast_a_rep_only_session_gets_no_reference(crm: Crm) -> None:
    n = nips.valid_nip(33101)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, body(X_NAME, n))
    rep_only = crm.login(REP_AND_MANAGER, ["rep"])
    answer = create(rep_only, full_body("Gospodarstwo K03 nowe", n, "K03"))
    assert answer.status_code == 409, answer.text
    assert answer.json() == NIP_TAKEN
    rep_b = crm.login(REP_B, ["rep"])
    assert same_answer(answer, create(rep_b, full_body("Gospodarstwo K03 nowe", n, "K03")))


def test_k03_a_manager_whose_own_customer_holds_the_nip_still_gets_the_reference(
    crm: Crm,
) -> None:
    n = nips.valid_nip(33202)
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    own = created_id(manager, body(X_NAME, n))
    answer = create(manager, body("Gospodarstwo K03 drugie", nips.spaced(n)))
    assert answer.status_code == 409, answer.text
    assert answer.json() == {**NIP_TAKEN, "existing_customer_id": own}


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(MANAGER, ["manager"], id="manager-only"),
        pytest.param(ADMINISTRATOR, ["administrator"], id="administrator-only"),
        pytest.param(ROLE_LESS, [], id="role-less"),
    ],
)
def test_k03_a_caller_without_rep_is_refused_whether_the_nip_is_taken(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    taken, untaken = nips.valid_nip(33303), nips.valid_nip(33404)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, body(X_NAME, taken))
    caller = crm.login(subject, roles)
    before = crm.counts()
    on_taken = create(caller, full_body("Gospodarstwo K03 nowe", taken, "K03"))
    on_untaken = create(caller, full_body("Gospodarstwo K03 nowe", untaken, "K03"))
    assert on_taken.status_code == 403, on_taken.text
    assert on_taken.json() == NOT_PERMITTED
    assert same_answer(on_taken, on_untaken)
    assert crm.counts() == before


def test_k03_the_reference_is_the_stored_customer_not_a_new_identifier(crm: Crm) -> None:
    n = nips.valid_nip(33505)
    rep_a = crm.login(REP_A, ["rep"])
    x = created_id(rep_a, body(X_NAME, n))
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    references = {
        create(manager, body("Gospodarstwo K03 nowe", n)).json()["existing_customer_id"]
        for _ in range(2)
    }
    assert references == {x}
    assert crm.pg.rows("SELECT id FROM customer WHERE nip = %s", (n,)) == [(uuid.UUID(x),)]
