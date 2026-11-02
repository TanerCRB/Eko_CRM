"""K-05, on demand: the command documented in backup/README.md runs a backup now and exits 0 only
once a complete set is at the destination; the double is read at the moment of exit.

Contrast: a double that accepts every write but loses the completion record; the command must
then exit non-zero, because no set is complete.
"""

import pytest

from tests.runtime.backup_lab import (
    BackupLab,
    complete_sets,
    failure_fields,
    failure_lines,
    set_names,
)

pytestmark = pytest.mark.runtime


def test_k05_the_documented_command_exits_0_once_the_set_is_complete(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    result = backup_lab.on_demand().wait()
    complete_at_exit = complete_sets(backup_lab.double) - before
    assert result.code == 0, result.stderr
    assert len(complete_at_exit) == 1


def test_k05_contrast_a_double_that_loses_the_last_object_fails_the_command(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    backup_lab.double.set_mode("lose-complete")
    try:
        result = backup_lab.on_demand().wait()
    finally:
        backup_lab.double.set_mode("on")
    assert result.code != 0
    [line] = failure_lines(result.stderr)
    assert failure_fields(line)["reason"] == "destination"
    assert not (set_names(backup_lab.double) - before) & complete_sets(backup_lab.double)
