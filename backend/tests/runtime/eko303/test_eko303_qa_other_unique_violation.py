"""EKO-3-03 QA (K-01 and K-04's "not a 503" boundary; impact map, design point 2): only a violation
of `uq_customer_nip` becomes the NIP refusal. A unique violation of another constraint on the
customer insert keeps the general storage-failure answer, 503, so the refusal never says a NIP is
taken when it is not, and nothing is stored.

The other violation is reached through a test-only path: the data layer's identifier generator is
made to return the identifier of a customer already stored, so the insert collides on the shipped
`customer_pkey` while its NIP is free. Production code is untouched. Contrast: the same create
with the generator left alone (the one changed element) is stored. Every value is synthetic and
every NIP is built at run time.
"""

import uuid

import pytest

from app.data import customers as data_customers
from tests.runtime.eko301.conftest import REP_A, REP_AND_MANAGER, REP_B, Crm, create, created_id
from tests.runtime.eko303.conftest import full_body, holders, stored_customer
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

UNAVAILABLE = {"detail": "temporarily unavailable"}
CALLERS = [
    pytest.param(REP_B, ["rep"], id="rep"),
    pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
]


@pytest.mark.parametrize(("subject", "roles"), CALLERS)
def test_qa_a_unique_violation_on_another_constraint_keeps_the_503_not_the_nip_refusal(
    crm: Crm, monkeypatch: pytest.MonkeyPatch, subject: str, roles: list[str]
) -> None:
    held_nip, free_nip = nips.valid_nip(38101), nips.valid_nip(38202)
    rep_a = crm.login(REP_A, ["rep"])
    held = created_id(rep_a, full_body("Gospodarstwo QA A", held_nip, "QAA"))
    caller = crm.login(subject, roles)
    before, row_before = crm.counts(), stored_customer(crm, held)

    monkeypatch.setattr(data_customers, "new_identifier", lambda: uuid.UUID(held))
    answer = create(caller, full_body("Gospodarstwo QA B", free_nip, "QAB"))

    assert answer.status_code == 503, answer.text
    assert answer.json() == UNAVAILABLE
    assert crm.counts() == before
    assert stored_customer(crm, held) == row_before
    assert holders(crm, free_nip) == []


@pytest.mark.parametrize(("subject", "roles"), CALLERS)
def test_qa_contrast_the_same_create_with_a_fresh_identifier_is_stored(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    held_nip, free_nip = nips.valid_nip(38101), nips.valid_nip(38202)
    rep_a = crm.login(REP_A, ["rep"])
    created_id(rep_a, full_body("Gospodarstwo QA A", held_nip, "QAA"))
    caller = crm.login(subject, roles)
    before = crm.counts()

    answer = create(caller, full_body("Gospodarstwo QA B", free_nip, "QAB"))

    assert answer.status_code == 201, answer.text
    assert crm.counts() == {
        "customer": before["customer"] + 1,
        "customer_contact": before["customer_contact"] + 2,
    }
    assert holders(crm, free_nip) == [(uuid.UUID(answer.json()["id"]), subject)]
