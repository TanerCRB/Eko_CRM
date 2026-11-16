"""QA, EKO-1-20 (ADR-0004 addendum 2026-11-08, gate-1 answer G-1 A): the bound ends each lock
wait on its own, not the snapshot transaction as a whole.

K-01's G-1-dependent edge: two application tables held in turn, each for less than the bound,
so the run waits longer than the bound in total. `alembic_version` is held first (the revision
read waits on it); just before it is released a second session takes `eko_test_backup_probe`
(the row counts wait on it). Under G-1 A each wait is shorter than the bound and the run
succeeds after about 240 s. A budget for the whole transaction (G-1 B, `transaction_timeout`)
ends it at about 180 s; the hit-the-bound tests cannot tell the two apart, because there one
wait alone outlasts the bound.
"""

import time

import pytest

from tests.runtime.backup_lab import BackupLab, complete_sets, failure_lines, set_names
from tests.runtime.test_eko120_control_lock_wait import (
    BOUND_SECONDS,
    POLL_SECONDS,
    PROBE,
    REVISIONS,
    control_waits_on,
    end_the_run,
    first_seen,
    table_held,
)

pytestmark = pytest.mark.runtime

# Each table is held this long after the control session is first seen waiting on it: well
# inside the bound, and together well past it.
IN_TURN = 120.0


def test_eko120_qa_k01_edge_two_tables_held_in_turn_within_the_bound_each_succeed(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    with table_held(backup_lab, REVISIONS) as first:
        run = backup_lab.start_run()
        try:
            seen = first_seen(
                backup_lab,
                f"the control session waits on {REVISIONS}",
                lambda: control_waits_on(backup_lab, REVISIONS),
                120,
            )
            while time.monotonic() < seen + IN_TURN:
                assert run.running(), f"the run ended while it waited on {REVISIONS}"
                assert backup_lab.dump_sessions() == []
                time.sleep(POLL_SECONDS)
            # The second lock is taken before the first is released, so the run never runs
            # free between the two waits.
            with table_held(backup_lab, PROBE) as second:
                first.query("COMMIT")
                second_seen = first_seen(
                    backup_lab,
                    f"the control session waits on {PROBE}",
                    lambda: control_waits_on(backup_lab, PROBE),
                    30,
                )
                while time.monotonic() < second_seen + IN_TURN:
                    assert run.running(), (
                        f"the run ended {time.monotonic() - seen:.1f} s after its first wait "
                        f"began, while it waited on {PROBE}"
                    )
                    assert backup_lab.dump_sessions() == []
                    time.sleep(POLL_SECONDS)
                released = time.monotonic()
                second.query("COMMIT")
            result = run.wait()
        finally:
            if run.running():
                end_the_run(backup_lab, run)
    # The two waits together outlasted the bound: a single budget would have ended the run.
    assert released - seen > BOUND_SECONDS + 30, f"the waits lasted {released - seen:.1f} s"
    assert result.code == 0, result.stderr
    assert failure_lines(result.output) == []
    new = set_names(backup_lab.double) - before
    assert len(new) == 1 and new <= complete_sets(backup_lab.double), new
