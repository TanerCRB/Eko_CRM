"""EKO-3-03 K-04 (ADR-0002 *NIP uniqueness*: the database constraint is the arbiter): two creates
with one NIP, overlapped by force, leave exactly one customer, and the loser gets the K-02 or K-03
refusal, not a 503.

The overlap is forced, not left to timing: the first create is held at its commit with its rows
written (`CommitGate`), the second is sent then, and its insert is seen waiting on the first
transaction in `pg_locks` before the first is released.
"""

import uuid

import pytest

from tests.runtime.eko301.conftest import REP_A, REP_AND_MANAGER, REP_B, Crm, create
from tests.runtime.eko303.conftest import (
    NIP_TAKEN,
    NIP_TAKEN_BODY,
    CommitGate,
    body,
    full_body,
    holders,
    overlapped,
    same_answer,
    second_browser,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

CONTACTS_OF = "SELECT value FROM customer_contact WHERE customer_id = %s ORDER BY position"


def test_k04_of_two_overlapping_creates_one_is_stored_and_the_loser_gets_the_rep_refusal(
    crm: Crm, gate: CommitGate
) -> None:
    n = nips.valid_nip(34101)
    rep_a = crm.login(REP_A, ["rep"])
    rep_b = crm.login(REP_B, ["rep"])
    result = overlapped(
        crm, gate, (rep_a, full_body("Gospodarstwo K04 A", n, "K04A")),
        (rep_b, full_body("Gospodarstwo K04 B", nips.hyphenated(n), "K04B")),
    )  # fmt: skip
    assert result.loser_waited, "the second insert never waited on the first transaction"
    assert result.winner.status_code == 201, result.winner.text
    assert result.loser.status_code == 409, result.loser.text
    assert result.loser.content == NIP_TAKEN_BODY
    winner_id = result.winner.json()["id"]
    assert holders(crm, n) == [(uuid.UUID(winner_id), REP_A)]
    assert crm.pg.rows(CONTACTS_OF, (winner_id,)) == [
        ("+48601303303",),
        ("k04a@farm.example.invalid",),
    ]
    assert crm.counts() == {"customer": 1, "customer_contact": 2}

    # The loser's answer is exactly the sequential rep refusal (K-02).
    sequential = create(rep_b, full_body("Gospodarstwo K04 B", n, "K04B"))
    assert same_answer(result.loser, sequential)


def test_k04_a_rep_and_manager_loser_gets_the_reference_to_the_winner(
    crm: Crm, gate: CommitGate
) -> None:
    n = nips.valid_nip(34303)
    rep_a = crm.login(REP_A, ["rep"])
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    result = overlapped(
        crm, gate, (rep_a, body("Gospodarstwo K04 A", n)),
        (manager, body("Gospodarstwo K04 M", n)),
    )  # fmt: skip
    assert result.loser_waited
    assert result.winner.status_code == 201, result.winner.text
    assert result.loser.status_code == 409, result.loser.text
    assert result.loser.json() == {**NIP_TAKEN, "existing_customer_id": result.winner.json()["id"]}
    assert crm.counts()["customer"] == 1


def test_k04_contrast_two_overlapping_creates_with_different_nips_are_both_stored(
    crm: Crm, gate: CommitGate
) -> None:
    n, other = nips.valid_nip(34404), nips.valid_nip(34505)
    rep_a = crm.login(REP_A, ["rep"])
    rep_b = crm.login(REP_B, ["rep"])
    result = overlapped(
        crm, gate, (rep_a, full_body("Gospodarstwo K04 A", n, "K04A")),
        (rep_b, full_body("Gospodarstwo K04 B", other, "K04B")),
    )  # fmt: skip
    assert not result.loser_waited
    assert (result.winner.status_code, result.loser.status_code) == (201, 201)
    assert crm.counts() == {"customer": 2, "customer_contact": 4}


def test_k04_when_the_winner_rolls_back_the_waiting_create_is_stored(
    crm: Crm, gate: CommitGate
) -> None:
    n = nips.valid_nip(34606)
    rep_a = crm.login(REP_A, ["rep"])
    rep_b = crm.login(REP_B, ["rep"])
    gate.fail = True
    result = overlapped(
        crm, gate, (rep_a, full_body("Gospodarstwo K04 A", n, "K04A")),
        (rep_b, full_body("Gospodarstwo K04 B", n, "K04B")),
    )  # fmt: skip
    assert result.loser_waited
    assert result.winner.status_code == 503, result.winner.text
    assert result.loser.status_code == 201, result.loser.text
    assert holders(crm, n) == [(uuid.UUID(result.loser.json()["id"]), REP_B)]
    assert crm.counts() == {"customer": 1, "customer_contact": 2}


def test_k04_a_double_submit_from_one_rep_stores_one_customer_and_refuses_the_other(
    crm: Crm, gate: CommitGate
) -> None:
    n = nips.valid_nip(34707)
    rep_a = crm.login(REP_A, ["rep"])
    again = second_browser(crm, rep_a)
    sent = full_body("Gospodarstwo K04 podwojne", n, "K04A")
    result = overlapped(crm, gate, (rep_a, sent), (again, sent))
    assert result.loser_waited
    assert result.winner.status_code == 201, result.winner.text
    assert result.loser.content == NIP_TAKEN_BODY
    assert result.loser.status_code == 409
    assert crm.counts() == {"customer": 1, "customer_contact": 2}
