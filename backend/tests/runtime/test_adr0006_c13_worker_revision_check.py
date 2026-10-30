"""K-02 / ADR-0006-C13 runtime half: on the shipped image, the worker refuses every database state
but its code's head and a recorded descendant, before it takes any job, and works on those two.

The worker is started with `compose run --no-deps` (restart policy "no"), so its one attempt's
exit code and state are read without a restart in between; restarts are backend's scenario.
"""

import time

import pytest

from tests.runtime.lab import (
    ACCEPTING_STATES,
    REFUSING_STATES,
    Lab,
    PsqlSession,
    configuration_values,
    container_state,
    docker,
)
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
EXIT_WITHIN_SECONDS = 30
SETTLE_SECONDS = 6
STARTED_LINE = "worker started"


def wait_for_exit(container: str) -> dict[str, object]:
    deadline = time.monotonic() + EXIT_WITHIN_SECONDS
    state = container_state(container)
    while state["Status"] != "exited" and time.monotonic() < deadline:
        time.sleep(0.3)
        state = container_state(container)
    return state


def logs_of(container: str) -> str:
    result = docker("logs", container, check=False)
    return result.stdout + result.stderr


@pytest.mark.parametrize("state", sorted(REFUSING_STATES))
def test_adr0006_c13_worker_revision_check_refuses(lab: Lab, state: str) -> None:
    REFUSING_STATES[state](lab)
    before = lab.comparison_dump()
    container = lab.start_worker()
    try:
        final = wait_for_exit(container)
        output = logs_of(container)
    finally:
        docker("rm", "-f", container, check=False)
    assert final["Status"] == "exited", final
    assert final["Running"] is False
    assert final["ExitCode"] != 0
    assert "worker refused to start" in output, output[-2000:]
    assert STARTED_LINE not in output
    assert mc.leaked_values(output, configuration_values(lab)) == []
    assert lab.comparison_dump() == before


@pytest.mark.parametrize("state", sorted(ACCEPTING_STATES))
def test_adr0006_c13_worker_revision_check_accepts(lab: Lab, state: str) -> None:
    ACCEPTING_STATES[state](lab)
    before = lab.comparison_dump()
    container = lab.start_worker()
    try:
        time.sleep(SETTLE_SECONDS)
        final = container_state(container)
        output = logs_of(container)
    finally:
        docker("rm", "-f", container, check=False)
    assert final["Running"] is True, output[-2000:]
    assert STARTED_LINE in output
    assert lab.comparison_dump() == before


def test_adr0006_c13_worker_never_waits_for_the_advisory_lock(lab: Lab) -> None:
    lab.at_head()
    holder = PsqlSession(lab.composition, name="eko-test-worker-holder")
    container = None
    try:
        holder.query("SELECT pg_advisory_lock(CAST(:'k' AS bigint))", k=str(KEY))
        container = lab.start_worker()
        time.sleep(SETTLE_SECONDS)
        final = container_state(container)
        output = logs_of(container)
    finally:
        holder.close()
        if container is not None:
            docker("rm", "-f", container, check=False)
    assert final["Running"] is True, output[-2000:]
    assert STARTED_LINE in output
