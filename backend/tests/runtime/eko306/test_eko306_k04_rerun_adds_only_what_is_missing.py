"""EKO-3-06 K-04 (C-3 A; gate 1 A-2 A, G-5 A): running the seed again adds only what is missing,
records without a NIP included, and changes nothing already loaded.

`uq_customer_nip` alone refuses a second copy of a Polish record with a NIP, so a re-run test
counting only those would pass with no record identity at all. The proof rests on the records the
constraint does not cover, each subset asserted on its own: Polish without a NIP, foreign with a
tax ID (never compared) and foreign without one.

- A second run with the same subjects leaves every customer and contact row byte-equal, ids
  included, reports that nothing was added and succeeds; so does a run naming other subjects
  (G-5 A: no owner changes).
- Resume: a run interrupted after k committed records, and one interrupted between a record's
  customer row and its contacts, completes on the next run with the value set of one
  uninterrupted run and no customer missing its contacts.
- Twin: a dataset NIP held by a customer a rep created first is reported under CUS-6, that
  customer is untouched and the run ends non-success; held by the earlier seed run instead, the
  result is "nothing added", success.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, event

from app.domain.customers import customer_draft
from app.seed_dataset import records
from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko303.conftest import rows_of
from tests.runtime.eko306.conftest import SEED_A, SEED_B_PRIME, SEED_C, SUBJECTS, Seeder, seeded
from tests.support.eko306_dataset import CANONICAL_ROWS, FINGERPRINT, fingerprint, stored_rows

pytestmark = pytest.mark.runtime

ROWS = {
    "customer": "SELECT c::text FROM customer c ORDER BY id",
    "customer_contact": "SELECT k::text FROM customer_contact k ORDER BY id",
}
COUNT = "SELECT count(*) FROM customer WHERE "
SUBSETS = {
    "polish-without-nip": COUNT + "country = 'PL' AND nip IS NULL",
    "foreign-with-tax-id": COUNT + "country <> 'PL' AND foreign_tax_id IS NOT NULL",
    "foreign-without-tax-id": COUNT + "country <> 'PL' AND foreign_tax_id IS NULL",
}


def rows(crm: Crm) -> dict[str, list[tuple[Any, ...]]]:
    return {table: rows_of(crm.pg, "eko", query) for table, query in ROWS.items()}


def dataset_subsets() -> dict[str, int]:
    drafts = [customer_draft(r.customer) for r in records()]
    return {
        "polish-without-nip": sum(1 for d in drafts if d.country == "PL" and d.tax_id.nip is None),
        "foreign-with-tax-id": sum(1 for d in drafts if d.country != "PL" and d.tax_id.foreign),
        "foreign-without-tax-id": sum(
            1 for d in drafts if d.country != "PL" and d.tax_id.foreign is None
        ),
    }


def stored_subsets(crm: Crm) -> dict[str, int]:
    return {name: int(rows_of(crm.pg, "eko", query)[0][0]) for name, query in SUBSETS.items()}


def test_k04_a_second_run_changes_no_row_and_reports_nothing_added(crm: Crm, seed: Seeder) -> None:
    first = seed()
    assert first.code == 0, first.lines
    expected = dataset_subsets()
    assert all(count > 0 for count in expected.values())
    assert stored_subsets(crm) == expected
    before = rows(crm)

    again = seed()
    assert again.code == 0, again.lines
    assert rows(crm) == before
    assert stored_subsets(crm) == expected
    assert again.totals() == {"total": 600, "added": 0, "already": 600, "refused": 0}
    assert any("nothing was added" in line for line in again.lines)


def test_k04_edge_a_run_naming_other_subjects_adds_nothing_and_changes_no_owner(
    crm: Crm, seed: Seeder
) -> None:
    assert seed().code == 0
    before = rows(crm)
    other = seed((SEED_C, SEED_B_PRIME, SEED_A))
    assert other.code == 0, other.lines
    assert rows(crm) == before
    assert {owner for _, _, owner in seeded(crm.pg)} == set(SUBJECTS)


class Interruption:
    """Stops the run, as an operator's Ctrl-C would, before a chosen statement of the seed."""

    def __init__(self, prefix: str, nth: int) -> None:
        self.prefix, self.nth, self.seen = prefix, nth, 0

    def __call__(self, conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        if statement.startswith(self.prefix):
            self.seen += 1
            if self.seen == self.nth:
                raise KeyboardInterrupt


@pytest.fixture
def interrupt() -> Iterator[list[Interruption]]:
    armed: list[Interruption] = []
    yield armed
    for listener in armed:
        event.remove(Engine, "before_cursor_execute", listener)


def arm(armed: list[Interruption], prefix: str, nth: int) -> None:
    listener = Interruption(prefix, nth)
    event.listen(Engine, "before_cursor_execute", listener)
    armed.append(listener)


def customers_without_their_contacts(crm: Crm) -> list[tuple[Any, ...]]:
    return rows_of(
        crm.pg,
        "eko",
        "SELECT c.dataset_key FROM customer c WHERE c.dataset_key IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM customer_contact k WHERE k.customer_id = c.id)",
    )


def without_contacts_in_the_dataset() -> set[str]:
    return {r.key for r in records() if not r.customer.contacts}


def test_k04_contrast_a_run_interrupted_after_k_records_is_completed_by_the_next(
    crm: Crm, seed: Seeder, interrupt: list[Interruption]
) -> None:
    arm(interrupt, "INSERT INTO customer ", 251)
    with pytest.raises(KeyboardInterrupt):
        seed()
    assert len(seeded(crm.pg)) == 250
    event.remove(Engine, "before_cursor_execute", interrupt.pop())

    resumed = seed()
    assert resumed.code == 0, resumed.lines
    assert resumed.totals() == {"total": 600, "added": 350, "already": 250, "refused": 0}
    assert fingerprint(stored_rows(rows_of(crm.pg, "eko", CANONICAL_ROWS))) == FINGERPRINT
    assert stored_subsets(crm) == dataset_subsets()


def test_k04_contrast_a_run_interrupted_between_a_customer_and_its_contacts_leaves_neither(
    crm: Crm, seed: Seeder, interrupt: list[Interruption]
) -> None:
    arm(interrupt, "INSERT INTO customer_contact ", 40)
    with pytest.raises(KeyboardInterrupt):
        seed()
    found = {key for _, key, _ in seeded(crm.pg)}
    assert found and len(found) < 600
    assert {
        k for (k,) in customers_without_their_contacts(crm)
    } <= without_contacts_in_the_dataset()
    event.remove(Engine, "before_cursor_execute", interrupt.pop())

    resumed = seed()
    assert resumed.code == 0, resumed.lines
    assert fingerprint(stored_rows(rows_of(crm.pg, "eko", CANONICAL_ROWS))) == FINGERPRINT
    assert {
        k for (k,) in customers_without_their_contacts(crm)
    } == without_contacts_in_the_dataset()


def first_record_with_a_nip() -> tuple[str, str]:
    for record in records():
        nip = customer_draft(record.customer).tax_id.nip
        if nip is not None:
            return record.key, nip
    raise AssertionError("the dataset holds no NIP")


def test_k04_contrast_a_dataset_nip_a_rep_created_first_is_refused_under_cus6(
    crm: Crm, seed: Seeder
) -> None:
    key, nip = first_record_with_a_nip()
    rep = crm.login(SEED_A, ["rep"])
    created = create(rep, {"name": "Gospodarstwo K04 bliźniak", "tax_id": nip})
    assert created.status_code == 201, created.text[:300]
    holder = rows_of(crm.pg, "eko", "SELECT c::text FROM customer c WHERE nip = %s", (nip,))

    run = seed()
    assert run.code != 0
    assert run.refused() == {key: ("CUS-6", "tax_id")}
    assert rows_of(crm.pg, "eko", "SELECT c::text FROM customer c WHERE nip = %s", (nip,)) == holder
    assert key not in {k for _, k, _ in seeded(crm.pg)}
    assert len(seeded(crm.pg)) == 599


def test_k04_contrast_the_same_nip_held_by_the_earlier_seed_run_is_nothing_added(
    crm: Crm, seed: Seeder
) -> None:
    key, nip = first_record_with_a_nip()
    assert seed().code == 0
    [(holder_key,)] = rows_of(
        crm.pg, "eko", "SELECT dataset_key FROM customer WHERE nip = %s", (nip,)
    )
    assert holder_key == key
    run = seed()
    assert run.code == 0, run.lines
    assert run.refused() == {}
    assert run.totals()["added"] == 0
