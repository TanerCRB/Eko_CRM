"""EKO-3-06 K-06 (C-2 A; ADR-0003-C37 and row 44, ADR-0004 *Migrations*, ADR-0003-C39): the seed
writes nothing but the dataset's own customers and their contacts.

The target holds, before the run: a customer of a named rep with two contacts, a customer with
the name, town and country of a no-NIP dataset record (a name twin), a customer of a subject the
run does not name, the staff display-name copies and sessions of their logins. The seed runs as
the operator runs it, `python -m app.seed`, in a process with the worker's environment only: no
identity-server address or secret at all, so it cannot reach Keycloak.

- Every pre-existing row of every table is byte-equal; `staff_display_name`, sessions, login
  transactions, `alembic_version` and `schema_revision_lineage` are unchanged; so are the
  schema's columns, constraints and indexes, `uq_customer_nip` among them.
- What changed is exactly the dataset's customers and contacts; the name twin's dataset record is
  loaded, so identity is not the name.
- No source the row-44 scan reads, the seed's two files among them, calls the admin API.

Contrast: the same snapshot sees the dataset's additions, so it is not blind.
"""

from collections import Counter

import pytest

from app.domain.customers import customer_draft
from app.seed_dataset import records
from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko306.conftest import SEED_A, UNNAMED, schema, seed_process, seeded, snapshot
from tests.static.test_eko202_no_admin_surface import admin_api_references, application_sources

pytestmark = pytest.mark.runtime

UNCHANGED_TABLES = (
    "staff_display_name",
    "app_session",
    "login_transaction",
    "alembic_version",
    "schema_revision_lineage",
)


def no_nip_record() -> tuple[str, str, str | None, str]:
    for record in records():
        draft = customer_draft(record.customer)
        if draft.country == "PL" and draft.tax_id.nip is None and draft.address.town:
            return record.key, draft.name, draft.address.town, draft.country
    raise AssertionError("no Polish record without a NIP but with a town")


def created(crm: Crm, subject: str, body: dict[str, object]) -> str:
    response = create(crm.login(subject, ["rep"]), body)
    assert response.status_code == 201, response.text[:300]
    return str(response.json()["id"])


def test_k06_the_diff_of_the_whole_database_is_exactly_the_dataset(crm: Crm) -> None:
    twin_key, twin_name, twin_town, twin_country = no_nip_record()
    created(
        crm,
        SEED_A,
        {
            "name": "Gospodarstwo K06 istniejące",
            "town": "Kutno",
            "contacts": [
                {"kind": "email", "value": "k06.a@seed.example"},
                {"kind": "email", "value": "k06.b@seed.example", "primary": True},
            ],
        },
    )
    created(crm, SEED_A, {"name": twin_name, "town": twin_town, "country": twin_country})
    created(crm, UNNAMED, {"name": "Gospodarstwo K06 nienazwane"})
    before, shape = snapshot(crm.pg), schema(crm.pg)
    assert before["staff_display_name"] and before["app_session"]

    done = seed_process(crm.pg)
    assert done.returncode == 0, done.stderr[-2000:]

    after = snapshot(crm.pg)
    assert schema(crm.pg) == shape
    assert any("uq_customer_nip" in str(row) for row in shape[1])
    for table in UNCHANGED_TABLES:
        assert after[table] == before[table], table
    assert set(after) == set(before)
    for table, rows in before.items():
        assert Counter(rows) - Counter(after[table]) == Counter(), table
    added = {table: len(after[table]) - len(rows) for table, rows in before.items()}
    contacts = sum(len(r.customer.contacts) for r in records())
    assert added == {**dict.fromkeys(before, 0), "customer": 600, "customer_contact": contacts}
    assert twin_key in {key for _, key, _ in seeded(crm.pg)}


def test_k06_the_admin_api_scan_reaches_the_seed_and_finds_no_call() -> None:
    sources = application_sources()
    assert {"seed.py", "seed_dataset.py"} <= set(sources)
    assert admin_api_references(sources) == []
