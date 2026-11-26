"""EKO-3-06, ADR-0005-C23, runtime half: `POST /api/customers` stores the dataset key as NULL, and
customers a rep creates never collide on it with each other or with seeded ones (NULLs distinct).
"""

import pytest

from tests.runtime.eko301.conftest import Crm, created_id
from tests.runtime.eko303.conftest import rows_of
from tests.runtime.eko306.conftest import SEED_A, Seeder

pytestmark = pytest.mark.runtime


def test_c23_create_stores_the_dataset_key_as_null(crm: Crm, seed: Seeder) -> None:
    assert seed().code == 0
    rep = crm.login(SEED_A, ["rep"])
    made = [created_id(rep, {"name": f"Gospodarstwo C23 {n}"}) for n in range(2)]
    keys = rows_of(
        crm.pg, "eko", "SELECT dataset_key FROM customer WHERE id = ANY(%s::uuid[])", (made,)
    )
    assert keys == [(None,), (None,)]
