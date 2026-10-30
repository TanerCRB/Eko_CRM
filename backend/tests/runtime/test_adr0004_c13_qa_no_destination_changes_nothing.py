"""R-01 fix (QA, EKO-1-11 verification): a command without a destination changes nothing.

`alembic ensure_version` carries no destination, so env.py runs it on the no-destination path,
and on an empty application database it creates an empty `alembic_version` table. Committed, that
is a state migrate refuses (K-03, empty `alembic_version` without lineage), so one diagnostic
command would block the next deployment. env.py's read-only transaction and its closing rollback
must leave the empty database as it was; either one alone is enough, so only removing both fails
this test.

`check` and `current` are here as well, for the developer's note that `check` on an empty
database now fails: Alembic itself never commits a change for them (`current` runs with
`dont_mutate`, and `check` raises "not up to date" before anything could be committed), so they
show the empty database is left alone, not that env.py's guards do it.

Contrast (one element changed, the command): `alembic upgrade head` on the same empty database
changes the comparison dump, so the dump does see a created `alembic_version`.
"""

import pytest

from tests.runtime.lab import Lab

pytestmark = pytest.mark.runtime

NO_DESTINATION = {
    "ensure-version": ("alembic", "ensure_version"),
    "current": ("alembic", "current"),
    "check": ("alembic", "check"),
}


@pytest.mark.parametrize("case", sorted(NO_DESTINATION))
def test_adr0004_c13_qa_no_destination_on_an_empty_database_changes_nothing(
    lab: Lab, case: str
) -> None:
    lab.reset()
    before = lab.comparison_dump()
    # The exit code is not the claim: on the empty database the read-only transaction makes
    # Alembic's own CREATE TABLE fail, so the command exits non-zero without changing anything.
    _, logs = lab.run_migrate(command=NO_DESTINATION[case])
    assert lab.versions() is None, logs[-2000:]
    assert lab.comparison_dump() == before


def test_adr0004_c13_qa_contrast_upgrade_head_on_an_empty_database_changes_the_dump(
    lab: Lab,
) -> None:
    lab.reset()
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(command=("alembic", "upgrade", "head"))
    assert code == 0, logs
    assert lab.versions() is not None
    assert lab.comparison_dump() != before
