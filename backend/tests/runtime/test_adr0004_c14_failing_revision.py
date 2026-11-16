"""K-04 / ADR-0004-C14: a failing revision applied through migrate exits non-zero, changes nothing,
lineage included, and the backend already running before the run keeps answering.

Variant F adds `t_c14_first` (valid) and `t_c14_second`, which fails after its first statement
succeeded; the contrast variant has only that failing statement removed.
"""

import time

import pytest

from tests.runtime.lab import SHIPPED_HEAD, Lab, restart_count

pytestmark = pytest.mark.runtime

WATCH_SECONDS = 20


def test_adr0004_c14_failing_revision(lab: Lab) -> None:
    container = lab.serving_backend()
    restarts = restart_count(container)
    image = lab.variant("c14_failing")
    before = lab.comparison_dump()
    watch = lab.watch_health(WATCH_SECONDS)
    started = time.monotonic()
    code, logs = lab.run_migrate(image)
    took = time.monotonic() - started
    statuses = watch.statuses()
    assert code != 0, logs
    assert '"cause":"psycopg.errors.DivisionByZero"' in logs, logs[-2000:]
    assert lab.comparison_dump() == before
    assert lab.versions() == [SHIPPED_HEAD]
    assert lab.lineage() == {"0001", "0002", "0003"}
    assert took < WATCH_SECONDS - 2, "the run outlasted the health watch"
    assert statuses and set(statuses) == {"200"}, statuses
    assert lab.composition.container_id("backend") == container
    assert restart_count(container) == restarts
    assert lab.health() == "200"


def test_adr0004_c14_contrast_without_the_failing_statement_both_revisions_apply(
    lab: Lab,
) -> None:
    lab.at_head()
    before = lab.comparison_dump()
    code, logs = lab.run_migrate(lab.variant("c14_passing"))
    assert code == 0, logs
    assert lab.versions() == ["t_c14_second"]
    assert lab.lineage() == {"0001", "0002", "0003", "t_c14_first", "t_c14_second"}
    assert lab.comparison_dump() != before
