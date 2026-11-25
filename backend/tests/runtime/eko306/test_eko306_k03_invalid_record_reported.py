"""EKO-3-06 K-03 (SEED-1, C-4 A): a record create's rules refuse is reported by its dataset key and
rule family (and field) and not loaded; every valid record of the same run is loaded; the run
ends non-success.

The dataset is run with one injected invalid record per family (CUS-2, CUS-3/CUS-4, CUS-5,
CUS-8): one first, two in the middle, one last.

Contrast: the same run with the four records corrected succeeds and reports no refused record.
Edges: exactly one invalid record; every record invalid (nothing stored, non-success).
"""

import pytest

from app.seed_dataset import Record, records
from tests.runtime.eko301.conftest import Crm
from tests.runtime.eko306.conftest import Seeder, seeded
from tests.support.eko306_cases import CASES

pytestmark = pytest.mark.runtime

INJECTED = {
    "k03-first": "cus2-country-xx",
    "k03-middle-a": "cus3-county-of-another-voivodeship",
    "k03-middle-b": "cus5-wrong-check-digit",
    "k03-last": "cus8-phone-12345",
}


def with_injected(corrected: bool = False) -> list[Record]:
    def one(key: str) -> Record:
        case = CASES[INJECTED[key]]
        return Record(key, 1, case.corrected if corrected else case.refused)

    dataset = list(records())
    middle = len(dataset) // 2
    return [
        one("k03-first"),
        *dataset[:middle],
        one("k03-middle-a"),
        one("k03-middle-b"),
        *dataset[middle:],
        one("k03-last"),
    ]


def test_k03_each_invalid_record_is_reported_with_its_rule_and_the_valid_ones_are_loaded(
    crm: Crm, seed: Seeder
) -> None:
    run = seed(records=with_injected())
    assert run.code != 0
    assert run.refused() == {
        key: (CASES[case].family, CASES[case].field) for key, case in INJECTED.items()
    }
    stored_keys = {key for _, key, _ in seeded(crm.pg)}
    assert stored_keys == {r.key for r in records()}
    assert run.totals() == {"total": 604, "added": 600, "already": 0, "refused": 4}


def test_k03_contrast_the_four_records_corrected_succeed_with_no_refusal(
    crm: Crm, seed: Seeder
) -> None:
    run = seed(records=with_injected(corrected=True))
    assert run.code == 0, run.lines
    assert run.refused() == {}
    assert {key for _, key, _ in seeded(crm.pg)} == {r.key for r in with_injected(True)}


def test_k03_edge_exactly_one_invalid_record(crm: Crm, seed: Seeder) -> None:
    dataset = list(records())
    one = Record("k03-one", 2, CASES["cus2-empty-name"].refused)
    run = seed(records=[*dataset[:10], one, *dataset[10:20]])
    assert run.code != 0
    assert run.refused() == {"k03-one": ("CUS-2", "name")}
    assert len(seeded(crm.pg)) == 20


def test_k03_edge_every_record_invalid_stores_nothing(crm: Crm, seed: Seeder) -> None:
    every = [Record(f"k03-all-{case}", 0, CASES[case].refused) for case in sorted(CASES)]
    run = seed(records=every)
    assert run.code != 0
    assert set(run.refused()) == {r.key for r in every}
    assert crm.counts() == {"customer_contact": 0, "customer": 0}
