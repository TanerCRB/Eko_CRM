"""EKO-1-31 (#162) — QA contrast carrier.

The committed K-01 guard (`test_eko131_reporting.py`) asserts the planted value is ABSENT from
the realm-scan failure report. An absence claim over a captured subprocess output is only
meaningful if the harness could have rendered the value in the first place: pytest 9.2 under a
traceback-shaping switch (`--tb=no`) suppresses the frame argument and the assert breakdown
altogether, so `K01_PLANT not in output` would pass on a tree that echoes every value, and the
alarm's own silence would be vacuous.

This module is the positive control for that claim. It drives the SAME child harness (imported
from the reporting module, so `-v`/ini/interpreter match K-01 exactly) over a failing test whose
assert breakdown legitimately carries the plant as a value — outside the realm family, where the
fix is not supposed to reach. The plant must appear. Together with K-01 (in-family: plant absent)
this is the contrast pair the role definition requires: the single changed element is which
machinery fails, and the echo expectation reverses with it.

The guard bites on any mechanism that would silently vacuify K-01 by suppressing value rendering
for the child (blanket `--tb`, a rewrite-disabling flag reaching the child) — it tests the
rendering directly, not only the two config strings the K-04 parse node reads.
"""

from pathlib import Path

import pytest

from tests.static.test_eko131_reporting import K01_PLANT, run_pytest_child

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# A plain failing assertion, built from the imported plant constant so no secret-shaped literal
# appears in this file's tracked text (the K-06 self-trap); the value is materialised only in the
# throwaway child written under tmp by the harness.
CONTROL_CHILD = (
    "def test_qa_k01_positive_control():\n"
    "    observed = 'not-the-plant'\n"
    f"    assert observed == {K01_PLANT!r}\n"
)


def test_eko131_qa_k01_positive_control_the_plant_renders_outside_the_family(
    tmp_path: Path,
) -> None:
    result = run_pytest_child(tmp_path, CONTROL_CHILD, "test_eko131_qa_control_child.py")
    output = result.stdout + result.stderr
    # (i) the child really failed and really produced a report — a missing report is not a control;
    assert result.returncode == 1, output[-3000:]
    assert "def test_qa_k01_positive_control():" in output, output[-3000:]
    # (ii) the harness renders the planted value when a value legitimately echoes into the report,
    # so K-01's `plant not in output` is a real constraint, not an unrenderable-string artifact.
    assert K01_PLANT in output, output[-3000:]
