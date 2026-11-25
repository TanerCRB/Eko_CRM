"""EKO-3-06 K-05 (C-1 A; ADR-0005-C22, ADR-0004-C37, G-7 A): the seed refuses a target not
declared synthetic-only, and one whose schema is not at its code's head, and writes nothing to it.

Against a target holding customers, staff copies and sessions: for an absent, empty or whitespace
declaration and every value but the accepted one, the run exits non-success, its output names the
missing declaration, and every table of the application database is byte-equal before and after.
The same holds for `python -m app.seed` in a process of its own, with the worker's environment.

Contrast: the identical target with only the declaration added loads the dataset.
Edge (G-7 A): a database at revision 0007, or at a revision the code cannot place, is refused
with nothing written; the seed never migrates it.
"""

from pathlib import Path

import pytest

from app.seed_dataset import SHARE_SIZE
from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko303.conftest import (
    connect_to,
    new_database,
    rows_of,
    run_migrate,
    tree_as_of_0007,
    versions,
)
from tests.runtime.eko306.conftest import (
    DECLARATION,
    SEED_A,
    Seeder,
    fresh_database,
    schema,
    seed_process,
    seeded,
    snapshot,
)
from tests.support.pg_instance import Postgres

pytestmark = pytest.mark.runtime

NOT_DECLARED = {
    "absent": None,
    "empty": "",
    "whitespace": "   ",
    "false": "false",
    "zero": "0",
    "true": "true",
    "case-variant": "Declared",
    "leading-space": " declared",
}


@pytest.fixture
def populated(crm: Crm) -> Crm:
    """A target that is not empty: a rep's customer, the rep's staff copy and session."""
    rep = crm.login(SEED_A, ["rep"])
    created = create(rep, {"name": "Gospodarstwo K05 istniejące", "town": "Kutno"})
    assert created.status_code == 201, created.text[:300]
    return crm


@pytest.mark.parametrize("case", sorted(NOT_DECLARED))
def test_k05_an_undeclared_target_is_refused_naming_the_declaration_and_unchanged(
    populated: Crm, seed: Seeder, case: str
) -> None:
    before = snapshot(populated.pg)
    run = seed(declared=NOT_DECLARED[case])
    assert run.code != 0
    assert run.refusal is not None and DECLARATION in run.refusal
    assert snapshot(populated.pg) == before


@pytest.mark.parametrize("case", ["absent", "false"])
def test_k05_the_operator_entry_point_refuses_an_undeclared_target(
    populated: Crm, case: str
) -> None:
    before = snapshot(populated.pg)
    done = seed_process(populated.pg, declared=NOT_DECLARED[case])
    assert done.returncode != 0
    assert DECLARATION in done.stderr
    assert snapshot(populated.pg) == before


def test_k05_contrast_the_same_target_with_only_the_declaration_added_loads(
    populated: Crm,
) -> None:
    done = seed_process(populated.pg)
    assert done.returncode == 0, done.stderr[-2000:]
    assert len(seeded(populated.pg)) == 3 * SHARE_SIZE


def test_k05_edge_a_target_at_an_older_revision_is_refused_and_not_migrated(
    pg: Postgres, seed: Seeder, tmp_path: Path
) -> None:
    database = "eko306_k05_at_0007"
    new_database(pg, database)
    code, output = run_migrate(pg, database, tree_as_of_0007(tmp_path))
    assert code == 0, output[-2000:]
    before, shape = snapshot(pg, database), schema(pg, database)
    run = seed(database=database)
    assert run.code != 0
    assert run.refusal is not None and "older than the code's head" in run.refusal
    assert versions(pg, database) == ["0007"]
    assert snapshot(pg, database) == before and schema(pg, database) == shape


def test_k05_edge_a_revision_the_code_cannot_place_is_refused(pg: Postgres, seed: Seeder) -> None:
    database = "eko306_k05_unplaceable"
    fresh_database(pg, database)
    with connect_to(pg, database) as connection:
        connection.execute("UPDATE alembic_version SET version_num = 'zz_unknown'")
    before = snapshot(pg, database)
    run = seed(database=database)
    assert run.code != 0
    assert run.refusal is not None and "not placeable" in run.refusal
    assert snapshot(pg, database) == before
    assert rows_of(pg, database, "SELECT count(*) FROM customer") == [(0,)]
