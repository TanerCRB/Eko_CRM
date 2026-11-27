"""EKO-4-01 QA contrasts: scenarios the developer suite passed through another mechanism, rewritten
so that only the criterion's own mechanism can give the expected answer.

- K-01 (b): in the developer's manager-only scenario the customer belongs to rep A, so the
  manager is refused by the ownership predicate and the all-records 403 (gate 1 A-2 A) even when
  the creation scope accepts `manager` without `rep`. Here the customer's owner is the manager's
  own subject (a staff member who held `rep` when the customer was stored and holds only
  `manager` now), so the role requirement of the creation scope is the only refusal left.
- K-01 (d): the visit rows are rewound to an earlier state (as a restore from a backup set leaves
  them), and the application plans again: no identifier it issued before the rewind comes back,
  which a generator derived from the highest stored identifier would hand out again.
- K-07 (c): the outbound recorder of the developer's K-07 test records `connect`; a call to a
  host that does not resolve fails in name resolution and never connects. This recorder also
  records every name lookup, so an outbound call is seen whether or not its host resolves.

Runtime, on real PostgreSQL and the OIDC stub; every value is synthetic.
"""

import socket
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.eko301.conftest import MANAGER, REP_A, Crm
from tests.runtime.eko401.conftest import (
    NOT_PERMITTED,
    customer,
    plan,
    planned_id,
    plant_customer,
    status_and_json,
    stored_visit,
    visit_body,
    visit_count,
)
from tests.runtime.eko401.test_eko401_k07_writes_only_the_visit_no_call_no_value_in_logs import (
    Scene,
    every_operation,
)

pytestmark = pytest.mark.runtime


def test_qa_k01_b_a_manager_only_caller_is_refused_for_a_customer_it_owns(crm: Crm) -> None:
    owned_by_the_manager = plant_customer(crm.pg, MANAGER, "Gospodarstwo Kierownika")
    manager = crm.login(MANAGER, ["manager"])
    assert status_and_json(plan(manager, visit_body(owned_by_the_manager))) == NOT_PERMITTED
    assert visit_count(crm.pg) == 0
    # Contrast: the same subject and customer, changing only the roles to `rep` and `manager`.
    both = crm.login(MANAGER, ["rep", "manager"])
    visit_id = planned_id(both, visit_body(owned_by_the_manager))
    assert stored_visit(crm.pg, visit_id)["owner_subject"] == MANAGER
    assert visit_count(crm.pg) == 1


def test_qa_k01_d_no_identifier_comes_back_after_the_visit_rows_are_rewound(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    own = customer(rep_a, "Gospodarstwo K01d")
    kept = {planned_id(rep_a, visit_body(own)) for _ in range(2)}
    lost = {planned_id(rep_a, visit_body(own)) for _ in range(4)}
    # The rewind: the rows planned after the "backup set" are gone, the earlier ones stay.
    removed = crm.pg.rows(
        "DELETE FROM visit WHERE id = ANY(CAST(%s AS uuid[])) RETURNING id::text", (sorted(lost),)
    )
    assert {row[0] for row in removed} == lost
    assert visit_count(crm.pg) == len(kept)
    again = {planned_id(rep_a, visit_body(own)) for _ in range(4)}
    assert again.isdisjoint(lost), "an identifier issued before the rewind was issued again"
    assert again.isdisjoint(kept)
    assert {uuid.UUID(identifier).version for identifier in again} == {4}


class Lookups:
    """Every name lookup and connection a Python socket of this process makes."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    def wrap(self, real: Any) -> Any:
        def recorded(*args: Any, **kwargs: Any) -> Any:
            self.seen.append(args[:2])
            return real(*args, **kwargs)

        return recorded


@pytest.fixture
def lookups(monkeypatch: pytest.MonkeyPatch) -> Iterator[Lookups]:
    recorder = Lookups()
    monkeypatch.setattr(socket, "getaddrinfo", recorder.wrap(socket.getaddrinfo))
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, recorder.wrap(getattr(socket.socket, name)))
    yield recorder


def test_qa_k07_c_no_visit_operation_looks_up_or_connects_to_any_host(
    crm: Crm, lookups: Lookups
) -> None:
    scene = Scene(crm)
    # Contrast: the logins are recorded, so a lookup or connection would be seen.
    assert lookups.seen, "the recorder saw no login lookup: it would see nothing"
    lookups.seen.clear()
    every_operation(scene)
    assert lookups.seen == []
