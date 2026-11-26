"""EKO-3-05 K-03, NIP taken on edit under concurrency (ADR-0003-C40; ADR-0002 *NIP uniqueness*: the
database constraint is the arbiter): an edit racing an edit or a create for one NIP leaves exactly
one holder; the loser gets the sequential refusal for its caller, never a 503.

The overlap is forced as in EKO-3-03 K-04: the first write is held at its commit with its row
written, the second is sent then and seen waiting on the first transaction in `pg_locks` before
the release. EKO-3-03's `CommitGate` fires only on `INSERT INTO customer `; the held edit needs a
gate on its `UPDATE`, which is this file's own `EditGate`.
"""

import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from sqlalchemy import Connection

from tests.runtime.eko301.conftest import REP_A, REP_AND_MANAGER, REP_B, Crm, create
from tests.runtime.eko303.conftest import (
    END_WAITING,
    INSERTED,
    NIP_TAKEN,
    CommitGate,
    holders,
    same_answer,
    waiting_inserts,
)
from tests.runtime.eko305.conftest import customer, edit, phone, snapshot
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

CUSTOMER_UPDATE = "UPDATE customer "


class EditGate(CommitGate):
    """EKO-3-03's gate, armed by the edit's `UPDATE` of a customer instead of its insert."""

    def _seen(self, conn: Connection, cursor: Any, statement: str, *rest: Any) -> None:
        if statement.startswith(CUSTOMER_UPDATE):
            conn.info[INSERTED] = True


@pytest.fixture
def edit_gate(crm: Crm) -> Iterator[EditGate]:
    held = EditGate(crm.app.state.database.engine)
    try:
        yield held
    finally:
        held.released.set()
        held.remove()


@pytest.fixture
def create_gate(crm: Crm) -> Iterator[CommitGate]:
    held = CommitGate(crm.app.state.database.engine)
    try:
        yield held
    finally:
        held.released.set()
        held.remove()


@dataclass
class Overlap:
    winner: httpx.Response
    loser: httpx.Response
    loser_waited: bool


Call = Callable[[], httpx.Response]


def overlapped(crm: Crm, gate: CommitGate, first: Call, second: Call) -> Overlap:
    """`first` reaches its commit and is held there; `second` is sent while it is held and the
    first is released once the second waits on the first transaction."""
    gate.armed = True
    futures: list[Future[httpx.Response]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            winner = pool.submit(first)
            futures.append(winner)
            if not gate.inserted.wait(30):
                raise AssertionError("the first write never reached its commit")
            loser = pool.submit(second)
            futures.append(loser)
            deadline = time.monotonic() + 20
            waited = False
            while time.monotonic() < deadline and not loser.done():
                if waiting_inserts(crm) == 1:
                    waited = True
                    break
                time.sleep(0.05)
            if not waited:
                loser.result(timeout=20)
            gate.released.set()
            return Overlap(winner.result(timeout=60), loser.result(timeout=60), waited)
        finally:
            gate.released.set()
            if not all(future.done() for future in futures):
                crm.pg.rows(END_WAITING)


def body(name: str, nip: str | None) -> dict[str, Any]:
    found: dict[str, Any] = {"name": name, "contacts": [phone("+48601305901", primary=True)]}
    if nip is not None:
        found["tax_id"] = nip
    return found


def row_of(crm: Crm, customer_id: str) -> tuple[Any, ...]:
    rows, contacts = snapshot(crm)
    return rows[customer_id], contacts.get(customer_id, [])


def test_k03_of_two_overlapping_edits_to_one_nip_one_is_stored_and_the_loser_refused(
    crm: Crm, edit_gate: EditGate
) -> None:
    n = nips.valid_nip(305901)
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    y, z = customer(rep_a, "Gospodarstwo Y"), customer(rep_b, "Gospodarstwo Z")
    z_before = row_of(crm, z)
    result = overlapped(
        crm,
        edit_gate,
        lambda: edit(rep_a, y, body("Gospodarstwo Y Po", n)),
        lambda: edit(rep_b, z, body("Gospodarstwo Z Po", nips.hyphenated(n))),
    )
    assert result.loser_waited, "the second edit never waited on the first transaction"
    assert result.winner.status_code == 200, result.winner.text
    assert result.loser.status_code == 409, result.loser.text
    assert holders(crm, n) == [(uuid.UUID(y), REP_A)]
    assert row_of(crm, z) == z_before
    sequential = edit(rep_b, z, body("Gospodarstwo Z Po", n))
    assert same_answer(result.loser, sequential)


def test_k03_a_create_waiting_on_a_held_edit_gets_the_managers_refusal_with_the_winner(
    crm: Crm, edit_gate: EditGate
) -> None:
    n = nips.valid_nip(305911)
    rep_a = crm.login(REP_A, ["rep"])
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    y = customer(rep_a, "Gospodarstwo Y")
    counts = crm.counts()
    result = overlapped(
        crm,
        edit_gate,
        lambda: edit(rep_a, y, body("Gospodarstwo Y Po", n)),
        lambda: create(manager, body("Gospodarstwo M", n)),
    )
    assert result.loser_waited
    assert result.winner.status_code == 200, result.winner.text
    assert result.loser.status_code == 409, result.loser.text
    assert result.loser.json() == {**NIP_TAKEN, "existing_customer_id": y}
    # The refused create stored nothing: one customer, and only the winner's new contact.
    assert crm.counts() == {"customer": counts["customer"], "customer_contact": 1}
    assert holders(crm, n) == [(uuid.UUID(y), REP_A)]


def test_k03_an_edit_waiting_on_a_held_create_gets_the_refusal(
    crm: Crm, create_gate: CommitGate
) -> None:
    n = nips.valid_nip(305921)
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    z = customer(rep_b, "Gospodarstwo Z")
    z_before = row_of(crm, z)
    result = overlapped(
        crm,
        create_gate,
        lambda: create(rep_a, body("Gospodarstwo Nowe A", n)),
        lambda: edit(rep_b, z, body("Gospodarstwo Z Po", n)),
    )
    assert result.loser_waited
    assert result.winner.status_code == 201, result.winner.text
    assert result.loser.status_code == 409, result.loser.text
    assert holders(crm, n) == [(uuid.UUID(result.winner.json()["id"]), REP_A)]
    assert row_of(crm, z) == z_before
    assert same_answer(result.loser, edit(rep_b, z, body("Gospodarstwo Z Po", n)))


def test_k03_edge_when_the_held_edit_rolls_back_the_waiting_edit_is_stored(
    crm: Crm, edit_gate: EditGate
) -> None:
    n = nips.valid_nip(305931)
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    y, z = customer(rep_a, "Gospodarstwo Y"), customer(rep_b, "Gospodarstwo Z")
    edit_gate.fail = True
    result = overlapped(
        crm,
        edit_gate,
        lambda: edit(rep_a, y, body("Gospodarstwo Y Po", n)),
        lambda: edit(rep_b, z, body("Gospodarstwo Z Po", n)),
    )
    assert result.loser_waited
    assert result.winner.status_code == 503, result.winner.text
    assert result.loser.status_code == 200, result.loser.text
    assert holders(crm, n) == [(uuid.UUID(z), REP_B)]
