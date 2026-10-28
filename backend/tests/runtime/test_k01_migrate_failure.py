"""K-01 edge: with `migrate` exiting non-zero, `backend` and `worker` never start."""

import pytest

from tests.runtime.conftest import Composition

pytestmark = pytest.mark.runtime

FAILING_MIGRATE = 'services:\n  migrate:\n    command: ["sh", "-c", "exit 3"]\n'


def test_k01_failed_migrate_keeps_backend_and_worker_from_starting(fresh: Composition) -> None:
    override = fresh.env_file.parent / "failing-migrate.yaml"
    override.write_text(FAILING_MIGRATE, encoding="utf-8")
    fresh.extra_files.append(override)
    up = fresh.compose("up", "--build", "--wait", "backend", "worker", check=False, timeout=900)
    assert up.returncode != 0
    assert "migrate" in up.stderr
    assert fresh.inspect("migrate")["State"]["ExitCode"] == 3
    for service in ("backend", "worker"):
        state = fresh.inspect(service)["State"]
        assert state["Running"] is False, service
        assert state["StartedAt"].startswith("0001-01-01"), service
