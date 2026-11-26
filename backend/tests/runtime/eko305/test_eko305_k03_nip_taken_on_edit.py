"""EKO-3-05 K-03, NIP taken on edit (ADR-0003-C40; ADR-0002 *NIP uniqueness*; D-5, D-6 X-2 A, X-3
A): a PUT setting a NIP another customer holds is refused exactly as EKO-3-03's create, by the
database's unique constraint `uq_customer_nip` on the edit's own scoped `UPDATE`. A rep's refusal
names nothing, whoever holds the NIP; a caller holding `manager`, with or without `rep`, also gets
`existing_customer_id`; a refused edit stores nothing. Keeping its own NIP is no conflict, an
archived holder keeps its NIP, and only that constraint is NIP-taken.

Fixtures: X of rep A holds N; Y of rep A and Z of rep B hold no N, each with an address and
contacts. Every target here is inside the caller's scope and active, so a refusal can come only
from the NIP (K-02 and K-04 prove the scope and the state come first). Every NIP is built at run
time (EKO-3-02 G-7 A).
"""

import uuid
from typing import Any

import httpx
import pytest

from app.data import customers as data_customers
from tests.runtime.eko201.conftest import FakeClock
from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_AND_MANAGER, REP_B, Crm, create
from tests.runtime.eko303.conftest import NIP_TAKEN, NIP_TAKEN_BODY, same_answer
from tests.runtime.eko305.conftest import (
    archive,
    customer,
    edit,
    email,
    phone,
    read_json,
    snapshot,
    status_and_json,
)
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

N = nips.valid_nip(305801)
SECOND = nips.valid_nip(305811)
UNUSED = nips.valid_nip(305821)


def stored(name: str, nip: str | None, marker: str) -> dict[str, Any]:
    found: dict[str, Any] = {
        "name": name,
        "street": f"ul. Stara {marker}",
        "postal_code": "05-805",
        "town": "Stara Wola",
        "contacts": [phone("+48601305801", f"Notatka {marker}", primary=True)],
    }
    if nip is not None:
        found["tax_id"] = nip
    return found


def changed(tax_id: Any, marker: str = "PO") -> dict[str, Any]:
    """Every field and the contacts changed as well as the tax ID."""
    return {
        "name": f"Gospodarstwo Zmienione {marker}",
        "street": f"ul. Nowa {marker}",
        "postal_code": "05-806",
        "town": "Nowa Wola",
        "voivodeship": "mazowieckie",
        "county": "Warszawa",
        "tax_id": tax_id,
        "contacts": [email(f"zmiana-{marker.lower()}@farm.example.invalid", primary=True)],
    }


@pytest.fixture
def scene(crm: Crm) -> dict[str, Any]:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    return {
        "rep_a": rep_a,
        "rep_b": rep_b,
        "x": customer(rep_a, **stored("Gospodarstwo X", N, "X")),
        "y": customer(rep_a, **stored("Gospodarstwo Y", None, "Y")),
        "z": customer(rep_b, **stored("Gospodarstwo Z", None, "Z")),
    }


def refused_unchanged(crm: Crm, send: Any) -> httpx.Response:
    before, counts = snapshot(crm), crm.counts()
    response: httpx.Response = send()
    assert snapshot(crm) == before
    assert crm.counts() == counts
    return response


def test_k03_a_reps_edit_to_a_taken_nip_is_refused_exactly_as_its_create(
    crm: Crm, scene: dict[str, Any]
) -> None:
    rep_a, rep_b = scene["rep_a"], scene["rep_b"]
    by_a = refused_unchanged(crm, lambda: edit(rep_a, scene["y"], changed(N)))
    by_b = refused_unchanged(crm, lambda: edit(rep_b, scene["z"], changed(nips.hyphenated(N))))
    assert by_a.status_code == 409, by_a.text
    assert by_a.content == NIP_TAKEN_BODY
    assert same_answer(by_a, by_b)
    created_a = refused_unchanged(crm, lambda: create(rep_a, changed(N)))
    created_b = refused_unchanged(crm, lambda: create(rep_b, changed(N)))
    assert same_answer(by_a, created_a)
    assert same_answer(by_b, created_b)


def test_k03_a_reps_refusal_is_the_same_whoever_holds_the_nip_and_for_a_second_one(
    crm: Crm, scene: dict[str, Any], clock: FakeClock
) -> None:
    rep_a, rep_b = scene["rep_a"], scene["rep_b"]
    baseline = edit(rep_a, scene["y"], changed(N))
    assert baseline.content == NIP_TAKEN_BODY, baseline.text
    customer(rep_b, **stored("Gospodarstwo B Drugie", SECOND, "B2"))
    held_by_b = refused_unchanged(crm, lambda: edit(rep_a, scene["y"], changed(SECOND)))
    assert archive(rep_a, scene["x"]).status_code == 200
    archived_holder = refused_unchanged(crm, lambda: edit(rep_a, scene["y"], changed(N)))
    for answer in (held_by_b, archived_holder):
        assert same_answer(answer, baseline)
        assert "existing_customer_id" not in answer.json()
    for value in (N, SECOND, scene["x"], REP_A, REP_B):
        assert value not in baseline.text
    assert not any(character.isdigit() for character in baseline.text)


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(REP_AND_MANAGER, ["rep", "manager"], id="rep-and-manager"),
        pytest.param(MANAGER, ["manager"], id="manager-without-rep"),
    ],
)
@pytest.mark.parametrize("holder_archived", [False, True], ids=["active-holder", "archived-holder"])
def test_k03_the_managers_refusal_carries_the_holder_which_reads_back(
    crm: Crm, scene: dict[str, Any], subject: str, roles: list[str], holder_archived: bool
) -> None:
    if holder_archived:
        assert archive(scene["rep_a"], scene["x"]).status_code == 200
    manager = crm.login(subject, roles)
    answer = refused_unchanged(crm, lambda: edit(manager, scene["y"], changed(N)))
    assert status_and_json(answer) == (409, {**NIP_TAKEN, "existing_customer_id": scene["x"]})
    resolved = read_json(manager, answer.json()["existing_customer_id"])
    assert (resolved["id"], resolved["tax_id"], resolved["archived"]) == (
        scene["x"],
        N,
        holder_archived,
    )


def test_k03_contrast_a_rep_never_gets_the_reference_even_to_its_own_holder(
    crm: Crm, scene: dict[str, Any]
) -> None:
    answer = edit(scene["rep_a"], scene["y"], changed(N))
    assert status_and_json(answer) == (409, NIP_TAKEN)


def test_k03_contrast_the_same_edit_with_an_unused_nip_is_stored(
    crm: Crm, scene: dict[str, Any]
) -> None:
    before = snapshot(crm)
    answer = edit(scene["rep_a"], scene["y"], changed(UNUSED))
    assert answer.status_code == 200, answer.text
    assert snapshot(crm) != before
    assert read_json(scene["rep_a"], scene["y"])["tax_id"] == UNUSED


def test_k03_keeping_its_own_nip_is_no_conflict(crm: Crm, scene: dict[str, Any]) -> None:
    answer = edit(scene["rep_a"], scene["x"], changed(nips.spaced(N), "X2"))
    assert answer.status_code == 200, answer.text
    record = read_json(scene["rep_a"], scene["x"])
    assert (record["name"], record["tax_id"]) == ("Gospodarstwo Zmienione X2", N)


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(lambda n: n, id="plain"),
        pytest.param(nips.hyphenated, id="hyphenated"),
        pytest.param(nips.spaced, id="spaced"),
        pytest.param(lambda n: "pl" + n, id="lower-case-pl"),
        pytest.param(lambda n: "PL" + n, id="upper-case-pl"),
        pytest.param(lambda n: "   " + n + "  ", id="surrounding-spaces"),
        pytest.param(lambda n: n[:5] + " " * 22 + n[5:], id="32-characters-as-sent"),
        pytest.param(lambda n: "PL " + nips.hyphenated(n), id="pl-space-hyphenated"),
    ],
)
def test_k03_every_spelling_create_accepts_collides_on_the_edit(
    crm: Crm, scene: dict[str, Any], spelling: Any
) -> None:
    written = spelling(N)
    assert len(written) <= 32
    on_edit = refused_unchanged(crm, lambda: edit(scene["rep_b"], scene["z"], changed(written)))
    on_create = refused_unchanged(crm, lambda: create(scene["rep_b"], changed(written)))
    assert same_answer(on_edit, on_create), (written, on_edit.text)


def test_k03_an_archived_holder_keeps_its_nip_for_create_and_edit(
    crm: Crm, scene: dict[str, Any]
) -> None:
    rep_b = scene["rep_b"]
    assert archive(scene["rep_a"], scene["x"]).status_code == 200
    assert refused_unchanged(crm, lambda: create(rep_b, changed(N))).content == NIP_TAKEN_BODY
    assert refused_unchanged(crm, lambda: edit(rep_b, scene["z"], changed(N))).content == (
        NIP_TAKEN_BODY
    )


def test_k03_another_unique_violation_on_the_edit_is_503_and_changes_nothing(
    crm: Crm, scene: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reached by a test-only path, as in `test_eko303_qa_other_unique_violation.py`: the data
    layer's identifier generator returns a stored contact's identifier, so the edit's contact
    insert collides on `customer_contact_pkey` while its NIP is free."""
    [(taken,)] = crm.pg.rows(
        "SELECT id FROM customer_contact WHERE customer_id = %s", (scene["x"],)
    )
    monkeypatch.setattr(data_customers, "new_identifier", lambda: uuid.UUID(str(taken)))
    answer = refused_unchanged(crm, lambda: edit(scene["rep_a"], scene["y"], changed(UNUSED)))
    assert status_and_json(answer) == (503, {"detail": "temporarily unavailable"})


def test_k03_contrast_the_same_edit_with_the_generator_left_alone_is_stored(
    crm: Crm, scene: dict[str, Any]
) -> None:
    answer = edit(scene["rep_a"], scene["y"], changed(UNUSED))
    assert answer.status_code == 200, answer.text


@pytest.mark.parametrize("cleared", ["omitted", "null", "empty"])
def test_k03_edge_clearing_the_nip_succeeds_and_two_customers_hold_none(
    crm: Crm, scene: dict[str, Any], cleared: str
) -> None:
    body = changed(N, "BEZ")
    if cleared == "omitted":
        body.pop("tax_id")
    else:
        body["tax_id"] = None if cleared == "null" else ""
    assert edit(scene["rep_a"], scene["x"], body).status_code == 200
    assert edit(scene["rep_a"], scene["y"], body).status_code == 200
    assert crm.pg.rows(
        "SELECT count(*) FROM customer WHERE nip IS NULL AND id = ANY(%s)",
        ([uuid.UUID(scene["x"]), uuid.UUID(scene["y"])],),
    ) == [(2,)]


def test_k03_edge_a_nip_swap_takes_three_edits(crm: Crm, scene: dict[str, Any]) -> None:
    rep_a, x, y = scene["rep_a"], scene["x"], scene["y"]
    m = SECOND
    assert edit(rep_a, y, changed(m, "Y")).status_code == 200
    swapped = refused_unchanged(crm, lambda: edit(rep_a, x, changed(m, "X")))
    assert swapped.content == NIP_TAKEN_BODY
    assert edit(rep_a, y, changed(None, "Y")).status_code == 200
    assert edit(rep_a, x, changed(m, "X")).status_code == 200
    assert edit(rep_a, y, changed(N, "Y")).status_code == 200
    assert (read_json(rep_a, x)["tax_id"], read_json(rep_a, y)["tax_id"]) == (m, N)


def test_k03_edge_a_foreign_tax_id_of_the_same_digits_does_not_collide(
    crm: Crm, scene: dict[str, Any]
) -> None:
    body = {**changed(N), "country": "DE", "voivodeship": None, "county": None}
    answer = edit(scene["rep_b"], scene["z"], body)
    assert answer.status_code == 200, answer.text
    assert read_json(scene["rep_b"], scene["z"])["tax_id"] == N


def test_k03_edge_a_malformed_body_carrying_a_taken_nip_keeps_its_422(
    crm: Crm, scene: dict[str, Any]
) -> None:
    body = {**changed(N), "postal_code": "5-5806"}
    on_edit = refused_unchanged(crm, lambda: edit(scene["rep_a"], scene["y"], body))
    on_create = create(scene["rep_a"], body)
    assert on_edit.status_code == 422, on_edit.text
    assert status_and_json(on_edit) == status_and_json(on_create)
