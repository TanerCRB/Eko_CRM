"""K-03, empty-table case on the narrower boundary (QA, EKO-1-11).

The empty-`alembic_version` case in test_adr0004_c13_migrate_revision_check.py starts from the
shipped head, so `schema_revision_lineage` is present. A migrate that took an empty
`alembic_version` for an empty database would still exit non-zero there, because revision 0002's
CREATE TABLE collides with the existing table; only the "migrate refused" log line tells that
failure from the descent check's refusal. Here the lineage table is absent too, so that mistake
would upgrade from the base and exit 0: only the descent check stands between the state and a
changed schema.

Contrast (one element changed): the same database without the `alembic_version` table is the
empty application database, which migrate upgrades from the base.
"""

import pytest

from tests.runtime.lab import SHIPPED_HEAD, SHIPPED_TREE, Lab

pytestmark = pytest.mark.runtime


def without_lineage(lab: Lab) -> None:
    lab.at_head()
    lab.drop_lineage()


def test_adr0004_c13_qa_empty_alembic_version_without_lineage_fails_and_changes_nothing(
    lab: Lab,
) -> None:
    without_lineage(lab)
    lab.set_versions([])
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code != 0, logs
    assert lab.comparison_dump() == before
    assert lab.versions() == []
    assert lab.lineage() is None


def test_adr0004_c13_qa_contrast_without_the_alembic_version_table_migrate_upgrades(
    lab: Lab,
) -> None:
    without_lineage(lab)
    lab.sql("DROP TABLE alembic_version")
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.versions() == [SHIPPED_HEAD]
    assert lab.lineage() == set(SHIPPED_TREE)
    assert lab.comparison_dump() != before
