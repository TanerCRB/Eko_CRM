"""R-01 / L-01 (EKO-1-11 verification): migrate runs migrations only for `alembic upgrade head`.

The database is at the shipped head and variant N has `t_next` pending, so any command that ran
migrations would change the comparison dump. An operator's override of migrate's command with
another destination is refused before anything is applied; `upgrade head` still applies.
"""

import pytest

from tests.runtime.lab import Lab

pytestmark = pytest.mark.runtime

REFUSED = {
    "upgrade-heads": ("alembic", "upgrade", "heads"),
    "downgrade-base": ("alembic", "downgrade", "base"),
    "stamp-head": ("alembic", "stamp", "head"),
    # Resolves to the code's head itself, so only the in-transaction step guard refuses it.
    "stamp-head-id": ("alembic", "stamp", "t_next"),
}


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_adr0004_c13_migrate_command_refusal(lab: Lab, case: str) -> None:
    lab.at_head()
    image = lab.variant("next")
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(image, command=REFUSED[case])
    assert code != 0, logs
    assert "migrate refused" in logs, logs[-2000:]
    assert lab.comparison_dump() == before


def test_adr0004_c13_migrate_command_refusal_contrast_upgrade_head_applies(lab: Lab) -> None:
    lab.at_head()
    image = lab.variant("next")
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(image, command=("alembic", "upgrade", "head"))
    assert code == 0, logs
    assert lab.versions() == ["t_next"]
    assert lab.lineage() == {"0001", "0002", "t_next"}
    assert lab.comparison_dump() != before
