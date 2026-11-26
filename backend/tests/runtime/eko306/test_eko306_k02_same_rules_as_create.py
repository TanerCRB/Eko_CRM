"""EKO-3-06 K-02 (CUS-1..CUS-5, CUS-8; gate 1 A-5 A): the seed accepts and stores a record exactly
as `POST /api/customers` does, and has no weaker path.

The seed loads into a database of its own on the test's server and the API creates into the
carriers' `eko`, so a NIP held on one side never collides with the other.

1. Every customer the dataset loads, read back and re-sent to `POST /api/customers`, gets 201 and
   is stored with the same values; no two loaded customers share a NIP.
2. Each K-02 case, injected into a run and sent to the API as a rep, is refused by both: 422
   from the API; reported with its family and field and not stored by the seed. Every case is one
   the database alone would accept (no nine-digit NIP, no second primary contact).
3. One injected record (a nine-digit national phone, an NFD name with surrounding spaces, a NIP
   spelled `PL 000-...`) and the same record created through the API store identical rows but
   for `id`, `owner_subject` and the dataset key.

Contrast: each refused case with its one value corrected is stored by the seed as create stores it.
"""

from collections.abc import Iterator
from typing import Any

import pytest

from app.seed_dataset import Record
from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko303.conftest import connect_to, rows_of
from tests.runtime.eko306.conftest import SEED_A, Seeder, fresh_database
from tests.support.eko306_cases import CASES, body, normalised_record
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

SIDE = "eko306_k02_side"
CUSTOMER = (
    "SELECT name, country, street, postal_code, town, voivodeship, county, nip, foreign_tax_id "
    "FROM customer WHERE id = %s"
)
CONTACTS = (
    "SELECT position, kind, value, note, is_primary FROM customer_contact WHERE customer_id = %s "
    "ORDER BY position"
)
BY_KEY = "SELECT id FROM customer WHERE dataset_key = %s"


@pytest.fixture(scope="module")
def side_database(pg: Postgres) -> str:
    fresh_database(pg, SIDE)
    return SIDE


@pytest.fixture
def side(pg: Postgres, side_database: str) -> Iterator[str]:
    with connect_to(pg, side_database) as connection:
        connection.execute("TRUNCATE customer_contact, customer")
    yield side_database


def stored(pg: Postgres, database: str, customer_id: Any) -> tuple[list[Any], list[Any]]:
    return (
        rows_of(pg, database, CUSTOMER, (customer_id,)),
        rows_of(pg, database, CONTACTS, (customer_id,)),
    )


def resent_body(row: tuple[Any, ...], contacts: list[tuple[Any, ...]]) -> dict[str, Any]:
    name, country, street, postal, town, voivodeship, county, nip, foreign = row
    found: dict[str, Any] = {"name": name, "country": country}
    for key, value in (
        ("street", street), ("postal_code", postal), ("town", town),
        ("voivodeship", voivodeship), ("county", county), ("tax_id", nip or foreign),
    ):  # fmt: skip
        if value is not None:
            found[key] = value
    found["contacts"] = [
        {"kind": kind, "value": value, "note": note, "primary": primary}
        for _, kind, value, note, primary in contacts
    ]
    return found


def test_k02_every_loaded_customer_is_one_create_stores_unchanged(
    crm: Crm, seed: Seeder, side: str
) -> None:
    run = seed(database=side)
    assert run.code == 0, run.lines
    rep = crm.login(SEED_A, ["rep"])
    loaded = rows_of(crm.pg, side, "SELECT id FROM customer ORDER BY dataset_key")
    assert len(loaded) == 600
    duplicated = "SELECT nip FROM customer WHERE nip IS NOT NULL GROUP BY nip HAVING count(*) > 1"
    assert rows_of(crm.pg, side, duplicated) == []
    for (customer_id,) in loaded:
        row, contacts = stored(crm.pg, side, customer_id)
        response = create(rep, resent_body(row[0], contacts))
        assert response.status_code == 201, response.text[:300]
        assert stored(crm.pg, "eko", response.json()["id"]) == (row, contacts)


@pytest.mark.parametrize("case", sorted(CASES))
def test_k02_each_case_is_refused_by_the_seed_and_by_create(
    crm: Crm, seed: Seeder, side: str, case: str
) -> None:
    found = CASES[case]
    key = f"k02-{case}"
    run = seed(records=[Record(key, 0, found.refused)], database=side)
    assert run.code != 0
    assert run.refused() == {key: (found.family, found.field)}
    assert rows_of(crm.pg, side, BY_KEY, (key,)) == []
    assert rows_of(crm.pg, side, "SELECT count(*) FROM customer_contact") == [(0,)]

    response = create(crm.login(SEED_A, ["rep"]), body(found.refused))
    assert response.status_code == 422, response.text[:300]
    assert {str(e["loc"][1]) for e in response.json()["detail"]} == {found.field.split(".")[0]}


@pytest.mark.parametrize("case", sorted(CASES))
def test_k02_contrast_each_corrected_case_is_stored_as_create_stores_it(
    crm: Crm, seed: Seeder, side: str, case: str
) -> None:
    found = CASES[case]
    key = f"k02-{case}"
    run = seed(records=[Record(key, 0, found.corrected)], database=side)
    assert run.code == 0, run.lines
    [(seeded_id,)] = rows_of(crm.pg, side, BY_KEY, (key,))
    response = create(crm.login(SEED_A, ["rep"]), body(found.corrected))
    assert response.status_code == 201, response.text[:300]
    assert stored(crm.pg, side, seeded_id) == stored(crm.pg, "eko", response.json()["id"])


def test_k02_a_normalised_record_is_stored_identically_by_the_seed_and_by_create(
    crm: Crm, seed: Seeder, side: str
) -> None:
    record = normalised_record()
    run = seed(records=[Record("k02-normalised", 0, record)], database=side)
    assert run.code == 0, run.lines
    [(seeded_id,)] = rows_of(crm.pg, side, BY_KEY, ("k02-normalised",))
    response = create(crm.login(SEED_A, ["rep"]), body(record))
    assert response.status_code == 201, response.text[:300]
    from_seed = stored(crm.pg, side, seeded_id)
    assert from_seed == stored(crm.pg, "eko", response.json()["id"])
    (name, *_rest, nip, _foreign), contacts = from_seed[0][0], from_seed[1]
    assert name == "Gospodarstwo Łąkowe Źrebię K02"
    assert nip is not None and len(nip) == 10 and nip.isdigit()
    assert contacts[0][2].startswith("+48") and contacts[1][2] == "k02.norm@seed.example"
