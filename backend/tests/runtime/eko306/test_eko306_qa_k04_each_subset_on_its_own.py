"""EKO-3-06 K-04, QA contrast: the re-run's count of each subset `uq_customer_nip` does not cover is
asserted on its own, so a duplicate in any one of them is named by that subset.

The developer test compares the whole row snapshot first, and that comparison already fails when
the seed's record identity is dropped; its per-subset assertion is then never reached. This test
keeps each subset's assertion independent of the snapshot and of the other subsets, so the claim
"no-NIP and foreign records do not duplicate" stands on records the NIP constraint never guards.

Contrast: one Polish customer without a NIP, created through the API between the two runs, is
counted by exactly that subset and by no other, so the counters are not blind.
"""

import pytest

from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko303.conftest import rows_of
from tests.runtime.eko306.conftest import SEED_A, Seeder
from tests.runtime.eko306.test_eko306_k04_rerun_adds_only_what_is_missing import (
    SUBSETS,
    dataset_subsets,
)

pytestmark = pytest.mark.runtime


def subset_count(crm: Crm, name: str) -> int:
    return int(rows_of(crm.pg, "eko", SUBSETS[name])[0][0])


@pytest.mark.parametrize("name", sorted(SUBSETS))
def test_qa_k04_a_re_run_leaves_each_non_nip_subset_at_the_dataset_count(
    crm: Crm, seed: Seeder, name: str
) -> None:
    expected = dataset_subsets()[name]
    assert expected > 0
    seed()
    assert subset_count(crm, name) == expected
    seed()
    assert subset_count(crm, name) == expected


def test_qa_k04_contrast_one_more_polish_customer_without_a_nip_is_counted_by_that_subset_only(
    crm: Crm, seed: Seeder
) -> None:
    assert seed().code == 0
    before = {name: subset_count(crm, name) for name in SUBSETS}
    created = create(crm.login(SEED_A, ["rep"]), {"name": "Gospodarstwo QA K04 bez NIP"})
    assert created.status_code == 201, created.text[:300]
    after = {name: subset_count(crm, name) for name in SUBSETS}
    assert {name: after[name] - before[name] for name in SUBSETS} == {
        "foreign-with-tax-id": 0,
        "foreign-without-tax-id": 0,
        "polish-without-nip": 1,
    }
