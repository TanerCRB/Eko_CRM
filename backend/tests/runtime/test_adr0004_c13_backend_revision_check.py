"""K-02 / ADR-0004-C13(a), backend: on the shipped image, backend refuses every database state but
its code's head and a recorded descendant, and serves on those two.

Each scenario starts backend with `compose up --no-deps` against a prepared database, so no
successful migrate runs in front of it: the refusal is the backend's own. The service keeps its
`restart: unless-stopped`, so "never answers" covers the attempts after a restart too.
"""

import json
import time

import pytest

from tests.runtime.lab import (
    ACCEPTING_STATES,
    REFUSING_STATES,
    Lab,
    PsqlSession,
    configuration_values,
    docker,
    exit_code_once_exited,
    health_body,
    restart_count,
)
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
REFUSAL_WINDOW_SECONDS = 40
MIN_OBSERVED_SECONDS = 8
NORMAL_START_SECONDS = 30


def start_backend(lab: Lab) -> str:
    lab.composition.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
    return lab.composition.container_id("backend")


@pytest.mark.parametrize("state", sorted(REFUSING_STATES))
def test_adr0004_c13_backend_revision_check_refuses(lab: Lab, state: str) -> None:
    REFUSING_STATES[state](lab)
    before = lab.comparison_dump()
    container = start_backend(lab)
    statuses = []
    try:
        started = time.monotonic()
        while time.monotonic() < started + REFUSAL_WINDOW_SECONDS:
            statuses.append(lab.health())
            observed = time.monotonic() - started
            if restart_count(container) >= 1 and observed > MIN_OBSERVED_SECONDS:
                break
            time.sleep(0.5)
        code = exit_code_once_exited(container)
        restarts = restart_count(container)
        logs = docker("logs", container, check=False)
    finally:
        lab.composition.compose("stop", "backend")
    output = logs.stdout + logs.stderr
    assert "200" not in statuses, statuses
    assert restarts >= 1
    assert code != 0
    assert "backend refused to start" in output, output[-2000:]
    assert mc.leaked_values(output, configuration_values(lab)) == []
    assert lab.comparison_dump() == before


@pytest.mark.parametrize("state", sorted(ACCEPTING_STATES))
def test_adr0004_c13_backend_revision_check_accepts(lab: Lab, state: str) -> None:
    ACCEPTING_STATES[state](lab)
    before = lab.comparison_dump()
    start_backend(lab)
    lab.wait_for_health("200", 90)
    # ADR-0003-C23: status only, no revision.
    assert json.loads(health_body(lab)) == {"status": "ok"}
    assert lab.comparison_dump() == before


def test_adr0004_c13_backend_never_waits_for_the_advisory_lock(lab: Lab) -> None:
    lab.at_head()
    holder = PsqlSession(lab.composition, name="eko-test-backend-holder")
    try:
        holder.query("SELECT pg_advisory_lock(CAST(:'k' AS bigint))", k=str(KEY))
        started = time.monotonic()
        start_backend(lab)
        lab.wait_for_health("200", NORMAL_START_SECONDS)
        took = time.monotonic() - started
        [[waiting]] = lab.sql("SELECT count(*) FROM pg_locks WHERE NOT granted")
    finally:
        holder.close()
    assert took < NORMAL_START_SECONDS
    assert waiting == "0"
