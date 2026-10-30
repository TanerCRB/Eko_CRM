"""K-03 / ADR-0004-C13(b)-(d): migrate's descent check, before Alembic resolves any revision.

The previous release is the shipped image (head 0002), the next release variant N adds `t_next`,
and the siblings X and Y add `t_sibling_b` and `t_sibling_a` (C-4). `t_next` is absent from the
shipped image, so accepting it proves the lineage record, not Alembic's graph.
"""

import json
from collections.abc import Callable

import pytest

from tests.runtime.lab import SHIPPED_HEAD, Lab, health_body

pytestmark = pytest.mark.runtime

LIST_VERSIONS = (
    "import os, sys; "
    "print('\\n'.join(sorted(os.listdir(sys.argv[1]))))"  # leftovers-allow: probe stdout
)
VERSIONS_DIR = "/app/migrations/versions"


def version_files(lab: Lab, image: str) -> list[str]:
    return lab.image_python(image, LIST_VERSIONS, VERSIONS_DIR).split()


def test_adr0004_c13_migrate_revision_check_precondition_t_is_absent_from_the_shipped_image(
    lab: Lab,
) -> None:
    assert "t_next.py" not in version_files(lab, lab.shipped_image)
    assert "t_next.py" in version_files(lab, lab.variant("next"))


def test_adr0004_c13_migrate_revision_check_b_previous_release_on_a_descendant(lab: Lab) -> None:
    lab.at_variant_head("next")
    assert lab.versions() == ["t_next"]
    assert lab.lineage() == {"0001", "0002", "t_next"}
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.comparison_dump() == before
    assert lab.lineage() == {"0001", "0002", "t_next"}
    lab.composition.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
    lab.wait_for_health("200", 90)
    assert json.loads(health_body(lab)) == {"status": "ok"}
    assert lab.comparison_dump() == before


def test_adr0004_c13_migrate_revision_check_c_sibling_is_refused(lab: Lab) -> None:
    lab.at_variant_head("sibling_b")
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(lab.variant("sibling_a"))
    assert code != 0, logs
    assert "migrate refused" in logs, logs[-2000:]
    assert lab.comparison_dump() == before


def test_adr0004_c13_migrate_revision_check_contrast_the_shipped_image_accepts_the_sibling(
    lab: Lab,
) -> None:
    lab.at_variant_head("sibling_b")
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.comparison_dump() == before


def _unknown(lab: Lab) -> None:
    lab.at_head()
    lab.set_versions(["zz_never_written"])


def _no_row(lab: Lab) -> None:
    lab.at_head()
    lab.set_versions([])


def _two_rows(lab: Lab) -> None:
    lab.at_head()
    lab.set_versions(["0001", "0002"])


UNPLACEABLE: dict[str, Callable[[Lab], None]] = {
    "c-unknown-identifier": _unknown,
    "empty-alembic-version": _no_row,
    "two-rows": _two_rows,
}


@pytest.mark.parametrize("state", sorted(UNPLACEABLE))
def test_adr0004_c13_migrate_revision_check_unplaceable_state_fails_and_changes_nothing(
    lab: Lab, state: str
) -> None:
    UNPLACEABLE[state](lab)
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code != 0, logs
    assert "migrate refused" in logs, logs[-2000:]
    assert lab.comparison_dump() == before


def test_adr0004_c13_migrate_revision_check_ancestor_is_upgraded_with_its_lineage(
    lab: Lab,
) -> None:
    lab.at_0001()
    assert lab.lineage() is None
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.versions() == [SHIPPED_HEAD]
    assert lab.lineage() == {"0001", "0002"}
    # The contrast of (d): the comparison sees a change when there is one.
    assert lab.comparison_dump() != before


def test_adr0004_c13_migrate_revision_check_d_second_run_at_head_changes_nothing(lab: Lab) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    code, logs = lab.run_migrate()
    assert code == 0, logs
    assert lab.comparison_dump() == before
