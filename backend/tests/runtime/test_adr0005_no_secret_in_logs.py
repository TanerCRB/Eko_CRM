"""EKO-1-13 K-07 (b): after the runtime tests that ran before it, no container log of the
development composition or of the EKO-1-11 lab holds any secret value of its environment file
(ADR-0004 *Secret handling*). The runtime conftest orders this file last.

Scope: the two session compositions this test can reach (`running`, `lab`), every container of
each project, exited ones included. EKO-1-14's backup lab has its own log-content test
(`test_adr0005_backup_log_content.py`). Contrast: a planted start-up line echoing
`APP_DB_PASSWORD` is found by the same check.
"""

import json
import re

import pytest

from tests.runtime.conftest import Composition, Started
from tests.runtime.lab import Lab, docker

pytestmark = pytest.mark.runtime

SECRET_NAME = re.compile(r"(PASSWORD|SECRET|KEY|CREDENTIAL|TOKEN)")


def secret_values(composition: Composition) -> dict[str, str]:
    return {name: value for name, value in composition.env.items()
            if SECRET_NAME.search(name) and len(value) >= 8}  # fmt: skip


def project_logs(composition: Composition) -> dict[str, str]:
    listed = docker(
        "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={composition.project}"
    ).stdout.split()
    logs = {}
    for container in listed:
        name = json.loads(docker("inspect", "-f", "{{json .Name}}", container).stdout)
        result = docker("logs", container, check=False, timeout=180)
        logs[name] = result.stdout + result.stderr
    return logs


def secret_problems(logs: dict[str, str], secrets: dict[str, str]) -> list[str]:
    return [f"{container}: holds {name}" for container, text in sorted(logs.items())
            for name, value in sorted(secrets.items()) if value in text]  # fmt: skip


@pytest.mark.parametrize("which", ["running", "lab"])
def test_adr0005_no_secret_in_logs(request: pytest.FixtureRequest, which: str) -> None:
    held = request.getfixturevalue(which)
    composition = held.composition if isinstance(held, Started | Lab) else held
    logs = project_logs(composition)
    secrets = secret_values(composition)
    assert logs and secrets, (sorted(logs), sorted(secrets))
    assert secret_problems(logs, secrets) == []


def test_adr0005_no_secret_in_logs_contrast_planted_line(running: Started) -> None:
    secrets = secret_values(running.composition)
    name = "APP_DB_PASSWORD"
    planted = {"backend": f"starting with {name} {secrets[name]}\n"}
    assert secret_problems(planted, secrets) == ["backend: holds APP_DB_PASSWORD"]
