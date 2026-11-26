"""EKO-3-05 K-04, the seed clause of ADR-0003-C41 (D-8 Y-2 A): a run of EKO-3-06's operator seed
over seeded customers that were edited and archived adds nothing and changes nothing.

The seed loads its committed dataset. Two of rep A's seeded customers are taken: one holding a NIP,
and one without a NIP, which `uq_customer_nip` does not cover, so for it "nothing added" rests on
the dataset key alone. Each is edited by its rep (name and contacts changed, the tax ID left as
stored), then archived at T. A second run with the same subjects succeeds, reports every record
already loaded, and leaves every customer and contact row byte-identical: both customers are still
archived at T, keep their dataset keys and keep the edited values, not the dataset's.

Contrast: the same second run, given one record the first run left out, adds exactly that record
and reports it added, while the edited, archived customers stay byte-identical.
"""

from typing import Any

import pytest

from app.domain.customers import customer_draft
from app.seed_dataset import Record, records
from tests.runtime.eko201.conftest import Browser, FakeClock
from tests.runtime.eko301.conftest import REP_A, REP_B, Crm
from tests.runtime.eko303.conftest import rows_of
from tests.runtime.eko305.conftest import archive, edit, phone, read_json, stored_row
from tests.runtime.eko306.conftest import SEED_C, Seeder

pytestmark = pytest.mark.runtime

SUBJECTS = (REP_A, REP_B, SEED_C)
ROWS = {
    "customer": "SELECT c::text FROM customer c ORDER BY id",
    "customer_contact": "SELECT k::text FROM customer_contact k ORDER BY id",
}


def rows(crm: Crm) -> dict[str, list[tuple[Any, ...]]]:
    return {table: rows_of(crm.pg, "eko", query) for table, query in ROWS.items()}


def picked() -> tuple[Record, Record]:
    """Rep A's first record holding a NIP and its first Polish record without one."""
    share = [r for r in records() if r.share == 0]
    with_nip = next(r for r in share if customer_draft(r.customer).tax_id.nip is not None)
    without_nip = next(
        r
        for r in share
        if customer_draft(r.customer).country == "PL"
        and customer_draft(r.customer).tax_id.nip is None
    )
    return with_nip, without_nip


def seeded_id(crm: Crm, key: str) -> str:
    [(customer_id,)] = crm.pg.rows("SELECT id::text FROM customer WHERE dataset_key = %s", (key,))
    return str(customer_id)


def edited(rep: Browser, customer_id: str, index: int) -> dict[str, Any]:
    """The stored customer as its rep reads it, with a new name and new contacts; the tax ID and
    every other field as stored."""
    stored = read_json(rep, customer_id)
    body = {k: v for k, v in stored.items() if k not in {"id", "archived", "contacts"}}
    body["name"] = f"Gospodarstwo Po Edycji K04 {index}"
    body["contacts"] = [phone(f"+48601305{490 + index}", "Po edycji K04", primary=True)]
    return body


def edit_and_archive(crm: Crm, clock: FakeClock, keys: tuple[str, ...]) -> dict[str, Any]:
    rep = crm.login(REP_A, ["rep"])
    instant = clock.now()
    ids = {}
    for index, key in enumerate(keys):
        customer_id = seeded_id(crm, key)
        response = edit(rep, customer_id, edited(rep, customer_id, index))
        assert response.status_code == 200, response.text
        assert archive(rep, customer_id).status_code == 200
        ids[key] = customer_id
    return {"instant": instant, "ids": ids}


def assert_kept(crm: Crm, changed: dict[str, Any]) -> None:
    for index, (key, customer_id) in enumerate(changed["ids"].items()):
        row = stored_row(crm, customer_id)
        assert row["dataset_key"] == key
        assert row["owner_subject"] == REP_A
        assert row["archived_at"] == changed["instant"]
        assert row["name"] == f"Gospodarstwo Po Edycji K04 {index}"


def test_k04_a_seed_run_over_an_edited_archived_seeded_customer_adds_and_changes_nothing(
    crm: Crm, clock: FakeClock, seed: Seeder
) -> None:
    first = seed(SUBJECTS)
    assert first.code == 0, first.lines
    with_nip, without_nip = picked()
    changed = edit_and_archive(crm, clock, (with_nip.key, without_nip.key))
    clock.advance(seconds=60)
    before = rows(crm)

    again = seed(SUBJECTS)
    assert again.code == 0, again.lines
    assert again.totals() == {"total": 600, "added": 0, "already": 600, "refused": 0}
    assert rows(crm) == before
    assert_kept(crm, changed)


def test_k04_contrast_a_seed_run_adds_only_the_record_left_out_and_keeps_the_changed_ones(
    crm: Crm, clock: FakeClock, seed: Seeder
) -> None:
    with_nip, without_nip = picked()
    left_out = next(r for r in records() if r.share == 1)
    first = seed(SUBJECTS, [r for r in records() if r.key != left_out.key])
    assert first.code == 0, first.lines
    changed = edit_and_archive(crm, clock, (with_nip.key, without_nip.key))
    before = rows(crm)

    again = seed(SUBJECTS)
    assert again.code == 0, again.lines
    assert again.totals() == {"total": 600, "added": 1, "already": 599, "refused": 0}
    after = rows(crm)
    added = seeded_id(crm, left_out.key)
    assert [r for r in after["customer"] if added not in r[0]] == before["customer"]
    assert [r for r in after["customer_contact"] if added not in r[0]] == before["customer_contact"]
    assert_kept(crm, changed)
