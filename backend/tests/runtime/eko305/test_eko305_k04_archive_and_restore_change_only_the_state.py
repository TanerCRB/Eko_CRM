"""EKO-3-05 K-04 (CUS-9; ADR-0005 *Archiving*; Q-4 B; ADR-0002-C13): archive and restore change only
`archived_at`. An archived customer stays readable by identifier, leaves the default list and keeps
every field and contact; restore brings back the row exactly as it was. A repeat archive or restore
succeeds and leaves the row byte-identical, the first instant kept. The instant comes from the
application's injected clock, frozen here, and no answer carries it. The round trip runs on a
customer created through the API and on one the operator seed stored, whose dataset key is part of
the row compared (D-8 Y-2 A).

The ADR-0004-C38 carrier against the published previous release is
`tests/runtime/test_eko305_k04_c38_previous_release_over_the_archived_state.py`.
"""

import concurrent.futures
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.api.customers import NipTakenProblem
from tests.runtime.eko201.conftest import FakeClock
from tests.runtime.eko301.conftest import MANAGER, REP_A, REP_B, Crm, create
from tests.runtime.eko305.conftest import (
    EMPTY,
    archive,
    archived_at,
    customer,
    edit,
    email,
    found,
    phone,
    read,
    read_json,
    restore,
    search,
    seeded_customer,
    snapshot,
)
from tests.runtime.eko306.conftest import Seeder
from tests.support import eko302_nip as nips

pytestmark = pytest.mark.runtime

FULL: dict[str, Any] = {
    "name": "Gospodarstwo Archiwum K04",
    "street": "ul. Archiwalna 4",
    "postal_code": "04-004",
    "town": "Archiwowo",
    "voivodeship": "mazowieckie",
    "county": "Warszawa",
    "contacts": [
        phone("+48601305401", "Notatka do zachowania", primary=True),
        email("archiwum-k04@farm.example.invalid", "Druga notatka K04"),
    ],
}


SEEDED_KEY = "eko305-k04-seeded-001"


def full_body() -> dict[str, Any]:
    return {**FULL, "tax_id": nips.valid_nip(305401)}


def row_of(crm: Crm, customer_id: str) -> tuple[Any, ...]:
    return snapshot(crm)[0][customer_id]


def contacts_of(crm: Crm, customer_id: str) -> list[tuple[Any, ...]]:
    return snapshot(crm)[1].get(customer_id, [])


def default_lists(crm: Crm, *browsers: Any) -> list[set[str]]:
    return [found(b, params) for b in browsers for params in (None, {"state": ""})]


@pytest.mark.parametrize("origin", ["api", "seeded", "seeded-without-nip"])
def test_k04_archive_changes_only_archived_at_and_restore_brings_the_row_back(
    crm: Crm, clock: FakeClock, seed: Seeder, origin: str
) -> None:
    rep, manager = crm.login(REP_A, ["rep"]), crm.login(MANAGER, ["manager"])
    body = full_body()
    if origin == "seeded-without-nip":
        body.pop("tax_id")
    key = None if origin == "api" else SEEDED_KEY
    if key is None:
        customer_id = customer(rep, **body)
    else:
        customer_id = seeded_customer(crm, seed, REP_A, key, body)
    # The dataset key is in the compared row, just before `archived_at`.
    assert row_of(crm, customer_id)[-2] == key
    by_id_before = read_json(rep, customer_id)
    row_before, contacts_before = row_of(crm, customer_id), contacts_of(crm, customer_id)
    counts_before = crm.counts()
    assert by_id_before["archived"] is False and row_before[-1] is None
    assert all(customer_id in ids for ids in default_lists(crm, rep, manager))

    archived_instant = clock.now()
    answered = archive(rep, customer_id)
    assert answered.status_code == 200, answered.text
    assert answered.headers.get_list("cache-control") == ["no-store"]
    assert answered.json() == {**by_id_before, "archived": True}
    assert read_json(rep, customer_id) == {**by_id_before, "archived": True}
    assert read_json(manager, customer_id) == {**by_id_before, "archived": True}
    row = row_of(crm, customer_id)
    assert row[:-1] == row_before[:-1]
    assert row[-1] == archived_instant
    assert contacts_of(crm, customer_id) == contacts_before
    assert crm.counts() == counts_before
    assert all(customer_id not in ids for ids in default_lists(crm, rep, manager))
    for params in ({"state": "archived"}, {"state": "both"}):
        assert customer_id in found(rep, params) and customer_id in found(manager, params)

    clock.advance(seconds=1)
    repeated = archive(manager, customer_id)
    assert (repeated.status_code, repeated.json()["archived"]) == (200, True)
    assert row_of(crm, customer_id) == row
    assert archived_at(crm, customer_id) == archived_instant

    restored = restore(rep, customer_id)
    assert restored.status_code == 200, restored.text
    assert restored.headers.get_list("cache-control") == ["no-store"]
    assert restored.json() == by_id_before
    assert row_of(crm, customer_id) == row_before
    assert contacts_of(crm, customer_id) == contacts_before
    assert crm.counts() == counts_before
    assert all(customer_id in ids for ids in default_lists(crm, rep, manager))

    again = restore(manager, customer_id)
    assert (again.status_code, again.json()) == (200, by_id_before)
    assert row_of(crm, customer_id) == row_before


def test_k04_contrast_restoring_an_active_customer_leaves_it_active(crm: Crm) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **full_body())
    row_before = row_of(crm, customer_id)
    restored = restore(rep, customer_id)
    assert (restored.status_code, restored.json()["archived"]) == (200, False)
    assert row_of(crm, customer_id) == row_before
    assert customer_id in found(rep)


def test_k04_the_instant_is_the_injected_clocks_not_the_databases(
    crm: Crm, clock: FakeClock
) -> None:
    clock.at = datetime(2001, 2, 3, 4, 5, 6, 789000, tzinfo=UTC)
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, "Gospodarstwo Zegar K04")
    assert archive(rep, customer_id).status_code == 200
    assert archived_at(crm, customer_id) == datetime(2001, 2, 3, 4, 5, 6, 789000, tzinfo=UTC)
    [(column_default,)] = crm.pg.rows(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'customer' AND column_name = 'archived_at'"
    )
    assert column_default is None


def test_k04_archived_at_is_in_no_answer_of_any_customer_operation(
    crm: Crm, clock: FakeClock
) -> None:
    clock.at = datetime(2003, 4, 5, 6, 7, 8, tzinfo=UTC)
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **full_body())
    answers = [archive(rep, customer_id), archive(rep, customer_id), read(rep, customer_id)]
    answers += [search(rep, {"state": state}) for state in ("archived", "both", "active")]
    answers += [restore(rep, customer_id), edit(rep, customer_id, {"name": "Bez Daty"})]
    answers += [create(rep, {"name": "Nowy Bez Daty"}), read(rep, customer_id), search(rep)]
    assert all(response.status_code in (200, 201) for response in answers)
    for response in answers:
        for form in ("archived_at", "2003-04-05", "06:07:08"):
            assert form not in response.text, (form, response.request.url)


def test_k04_edge_a_customer_with_nothing_but_a_name_survives_the_round_trip(
    crm: Crm,
) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, "Gospodarstwo Puste K04")
    before = read_json(rep, customer_id)
    row_before = row_of(crm, customer_id)
    assert archive(rep, customer_id).json() == {**before, "archived": True}
    assert restore(rep, customer_id).json() == before
    assert row_of(crm, customer_id) == row_before


def test_k04_edge_a_reps_only_customer_archived_leaves_an_empty_default_list(crm: Crm) -> None:
    rep_a = crm.login(REP_A, ["rep"])
    customer(crm.login(REP_B, ["rep"]), "Gospodarstwo B K04")
    only = customer(rep_a, "Jedyne Gospodarstwo K04")
    assert archive(rep_a, only).status_code == 200
    assert search(rep_a).json() == EMPTY
    assert search(rep_a, {"state": ""}).json() == EMPTY


def test_k04_edge_a_double_archive_at_once_stores_one_instant(crm: Crm, clock: FakeClock) -> None:
    rep = crm.login(REP_A, ["rep"])
    customer_id = customer(rep, **full_body())
    first_instant = clock.now()
    second = crm.login(REP_A, ["rep"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda browser: archive(browser, customer_id), (rep, second)))
    assert [(a.status_code, a.json()["archived"]) for a in answers] == [(200, True)] * 2
    assert archived_at(crm, customer_id) == first_instant


def test_k04_a_row_stored_without_naming_the_state_is_active(crm: Crm) -> None:
    """K-04 M-p5: an `INSERT` that names no `archived_at`, as the previous release writes one,
    stores an active customer, so head reads it back `archived: false` in the default list."""
    rep = crm.login(REP_A, ["rep"])
    planted = str(uuid.uuid4())
    with crm.pg.connect() as connection:
        connection.execute(
            "INSERT INTO customer (id, name, country, owner_subject) VALUES (%s, %s, 'PL', %s)",
            (planted, "Gospodarstwo Poprzednie K04", REP_A),
        )
    assert read_json(rep, planted)["archived"] is False
    assert planted in found(rep)
    assert {item["id"]: item["archived"] for item in search(rep).json()["items"]} == {
        planted: False
    }


RESTORE_FIRST = (409, {"detail": "restore it first"})


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(REP_A, ["rep"], id="owner"),
        pytest.param(MANAGER, ["manager"], id="manager"),
    ],
)
def test_k04_editing_an_archived_customer_is_refused_409_and_changes_nothing(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    owner = crm.login(REP_A, ["rep"])
    customer_id = customer(owner, **full_body())
    assert archive(owner, customer_id).status_code == 200
    editor = crm.login(subject, roles)
    body = {"name": "Gospodarstwo Po Archiwum K04", "contacts": [phone("+48601305499")]}
    before = snapshot(crm)
    refused = edit(editor, customer_id, body)
    assert (refused.status_code, refused.json()) == RESTORE_FIRST
    assert refused.content == b'{"detail":"restore it first"}'
    assert refused.headers.get_list("cache-control") == ["no-store"]
    assert snapshot(crm) == before
    # Contrast: only the state differs; once restored, the same PUT is stored.
    assert restore(editor, customer_id).status_code == 200
    accepted = edit(editor, customer_id, body)
    assert accepted.status_code == 200, accepted.text
    assert read_json(owner, customer_id)["name"] == "Gospodarstwo Po Archiwum K04"


def test_k04_the_put_declares_409_as_create_does_and_restore_first_is_an_instance(
    crm: Crm,
) -> None:
    paths = crm.app.openapi()["paths"]
    put = paths["/api/customers/{customer_id}"]["put"]["responses"]["409"]
    post = paths["/api/customers"]["post"]["responses"]["409"]
    schema = put["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/NipTakenProblem"}
    assert schema == post["content"]["application/json"]["schema"]
    instance = NipTakenProblem.model_validate({"detail": "restore it first"})
    assert instance.body() == {"detail": "restore it first"}


TAKEN = nips.valid_nip(305481)


@pytest.mark.parametrize(
    ("subject", "roles"),
    [
        pytest.param(REP_A, ["rep"], id="owner"),
        pytest.param(MANAGER, ["manager"], id="manager"),
    ],
)
def test_k04_an_archived_customers_edit_to_a_taken_nip_answers_restore_first(
    crm: Crm, subject: str, roles: list[str]
) -> None:
    owner = crm.login(REP_A, ["rep"])
    holder = customer(owner, "Gospodarstwo Posiadacz K04", tax_id=TAKEN)
    customer_id = customer(owner, **full_body())
    assert archive(owner, customer_id).status_code == 200
    editor = crm.login(subject, roles)
    body = {"name": "Gospodarstwo NIP K04", "tax_id": TAKEN}
    before = snapshot(crm)
    refused = edit(editor, customer_id, body)
    assert refused.content == b'{"detail":"restore it first"}', refused.text
    assert refused.status_code == 409
    assert snapshot(crm) == before
    # Contrast: only the state differs; once restored, the same PUT meets the NIP.
    assert restore(editor, customer_id).status_code == 200
    taken = edit(editor, customer_id, body)
    expected: dict[str, Any] = {
        "detail": "a customer with this NIP already exists - contact your manager"
    }
    if subject == MANAGER:
        expected["existing_customer_id"] = holder
    assert (taken.status_code, taken.json()) == (409, expected)


def test_k04_an_archived_holder_keeps_its_nip_and_is_restored_with_it(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    holder = customer(rep_a, "Gospodarstwo Posiadacz K04", tax_id=TAKEN)
    assert archive(rep_a, holder).status_code == 200
    assert create(rep_b, {"name": "Gospodarstwo B K04", "tax_id": TAKEN}).status_code == 409
    restored = restore(rep_a, holder)
    assert (restored.status_code, restored.json()["tax_id"]) == (200, TAKEN)
