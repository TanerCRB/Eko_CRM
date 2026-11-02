"""K-01 (ADR-0004-C19): a run started by the schedule file's command completes under eko_backup's
CONNECTION LIMIT 5, and it needs every session it was observed to hold.

The server enforces the limit, so the run succeeding under 5 is the proof; the sampled maximum is
a record. The contrast sets the limit to that maximum minus one, and the same run must fail.
"""

import sys
from collections.abc import Callable

import pytest

from tests.runtime.backup_lab import (
    BackupLab,
    SessionSampler,
    complete_sets,
    failure_fields,
    failure_lines,
    set_names,
    unique_marker,
)

pytestmark = pytest.mark.runtime

LIMIT = 5


def sampled_run(backup_lab: BackupLab) -> tuple[int, set[str], int]:
    """One scheduled-path run that first waits on the advisory lock: (exit, new sets, maximum)."""
    before = set_names(backup_lab.double)
    with SessionSampler(backup_lab.composition) as sampler:
        with backup_lab.advisory_lock_held():
            run = backup_lab.start_run()
            backup_lab.wait_until(
                "the run waits for the advisory lock",
                lambda: ("eko", "eko-backup-control", "Lock") in backup_lab.backup_sessions(),
            )
        result = run.wait()
    assert sampler.samples > 0
    return result.code, set_names(backup_lab.double) - before, sampler.maximum


def test_k01_scheduled_entry_run_completes_within_the_limit(
    backup_lab: BackupLab, record_property: Callable[[str, object], None]
) -> None:
    backup_lab.at_probe_head()
    backup_lab.plant_row(unique_marker("k01"))
    [[limit]] = backup_lab.sql("SELECT rolconnlimit FROM pg_roles WHERE rolname = 'eko_backup'")
    assert int(limit) == LIMIT
    code, new, maximum = sampled_run(backup_lab)
    record_property("eko_backup_max_sessions", maximum)
    note = f"eko_backup sessions, sampled maximum: {maximum}\n"
    sys.stdout.write(note)  # leftovers-allow: K-01 records the sampled maximum in the output
    assert code == 0
    assert len(new) == 1
    assert new <= complete_sets(backup_lab.double)
    assert 1 <= maximum <= LIMIT


def test_k01_contrast_the_limit_below_the_observed_maximum_fails_the_run(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    code, _, maximum = sampled_run(backup_lab)
    assert code == 0
    # Limit 0 would prove only that the role cannot connect, not that the run fits.
    assert maximum > 1, "observed maximum 1: the contrast is void"
    before = set_names(backup_lab.double)
    backup_lab.sql("ALTER ROLE eko_backup CONNECTION LIMIT :n", n=str(maximum - 1))
    try:
        result = backup_lab.run()
    finally:
        backup_lab.sql("ALTER ROLE eko_backup CONNECTION LIMIT :n", n=str(LIMIT))
    assert result.code != 0
    [line] = failure_lines(result.stderr)
    assert failure_fields(line).get("sqlstate") == "53300", line
    assert not (set_names(backup_lab.double) - before) & complete_sets(backup_lab.double)
