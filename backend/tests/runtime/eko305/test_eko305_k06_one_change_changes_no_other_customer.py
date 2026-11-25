"""EKO-3-05 K-06 (PRH-5, CUS-9; prohibition): editing, archiving or restoring one customer changes
no other customer. Every customer row (`archived_at` included) and every contact row other than the
target's is compared before and after each operation.

The scenario holds other customers of the target's own owner, so a write that lost its per-customer
condition but kept the scope still changes rows here: a sibling with the target's name and NIP, and
a sibling archived at an earlier instant, both with contacts; and a customer of another rep. In
each case the target's own row did change, so an operation that does nothing cannot pass.
"""

import concurrent.futures
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.runtime.eko201.conftest import Browser, FakeClock
from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_B, Crm
from tests.runtime.eko305.conftest import (
    archive,
    archived_at,
    customer,
    edit,
    email,
    others,
    phone,
    restore,
    snapshot,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

TWIN_NAME = "Gospodarstwo Bliźniak K06"
SIBLING_NIP = nips.valid_nip(305612)


def edited_body() -> dict[str, Any]:
    return {
        "name": "Gospodarstwo Po Zmianie K06",
        "town": "Nowa Wola K06",
        "tax_id": nips.valid_nip(305601),
        "contacts": [phone("+48601305611", primary=True), email("po-zmianie-k06@example.com")],
    }


@pytest.fixture
def scene(crm: Crm, clock: FakeClock) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    # The sibling is the target's twin in name, address and contact values, with its own NIP: no
    # two customers hold one NIP (K-06 edge, the unique constraint of EKO-3-03).
    twin: dict[str, Any] = {
        "name": TWIN_NAME,
        "street": "ul. Bliźniacza 6",
        "town": "Bliźniaków",
        "tax_id": nips.valid_nip(305602),
        "contacts": [phone("+48601305621", "Notatka K06", primary=True)],
    }
    target = customer(rep_a, **twin)
    sibling = customer(rep_a, **{**twin, "tax_id": SIBLING_NIP})
    archived_sibling = customer(
        rep_a, "Gospodarstwo Uśpione K06", contacts=[email("uspione-k06@example.com")]
    )
    earlier = clock.now()
    assert archive(rep_a, archived_sibling).status_code == 200
    clock.advance(seconds=5)
    other_rep = customer(rep_b, TWIN_NAME, contacts=[phone("+48601305631", primary=True)])
    return {
        "rep_a": rep_a,
        "manager": crm.login(MANAGER, ["manager"]),
        "target": target,
        "sibling": sibling,
        "archived_sibling": archived_sibling,
        "earlier": earlier,
        "other_rep": other_rep,
    }


Step = Callable[[Browser, str], httpx.Response]
STEPS: dict[str, list[tuple[str, Step]]] = {
    "rep-edit": [("rep_a", lambda b, i: edit(b, i, edited_body()))],
    "manager-edit": [("manager", lambda b, i: edit(b, i, edited_body()))],
    "rep-archive-then-restore": [("rep_a", archive), ("rep_a", restore)],
    "manager-archive-then-restore": [("manager", archive), ("manager", restore)],
}


@pytest.mark.parametrize("case", sorted(STEPS))
def test_k06_a_change_of_one_customer_changes_no_other_row(
    crm: Crm, scene: dict[str, Any], case: str
) -> None:
    target = scene["target"]
    for caller, step in STEPS[case]:
        before = snapshot(crm)
        response = step(scene[caller], target)
        assert response.status_code == 200, (case, response.text)
        after = snapshot(crm)
        assert others(after, target) == others(before, target), case
        # The target's own row or contacts did change, so a no-op cannot pass.
        assert (after[0][target], after[1].get(target)) != (
            before[0][target],
            before[1].get(target),
        ), case
    assert archived_at(crm, scene["archived_sibling"]) == scene["earlier"]
    assert archived_at(crm, scene["sibling"]) is None


def test_k06_edge_a_double_submitted_edit_ends_in_one_state_and_leaves_the_siblings(
    crm: Crm, scene: dict[str, Any]
) -> None:
    target = scene["target"]
    second = crm.login(REP_A, ["rep"])
    before = snapshot(crm)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda b: edit(b, target, edited_body()), (scene["rep_a"], second)))
    assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
    assert answers[0].content == answers[1].content
    after = snapshot(crm)
    assert others(after, target) == others(before, target)
    assert [row[2:] for row in after[1][target]] == [
        (0, "phone", "+48601305611", None, True),
        (1, "email", "po-zmianie-k06@example.com", None, False),
    ]
    assert archived_at(crm, scene["archived_sibling"]) == scene["earlier"]


def test_k06_edge_an_edit_refused_for_a_taken_nip_changes_no_other_row(
    crm: Crm, scene: dict[str, Any]
) -> None:
    target = scene["target"]
    before = snapshot(crm)
    refused = edit(scene["rep_a"], target, {**edited_body(), "tax_id": SIBLING_NIP})
    assert refused.status_code == 409, refused.text
    assert snapshot(crm) == before
