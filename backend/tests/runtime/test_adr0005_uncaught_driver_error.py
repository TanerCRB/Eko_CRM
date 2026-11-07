"""EKO-1-13 K-05: outside a request, a driver or start-up error in `migrate`, `backend` or
`worker` exits non-zero and names only the error's type and code location, never the marker,
`[SQL`, `[parameters`, the database URL, host, role or password (ADR-0005 addendum of 2026-11-02,
*An error outside a request*, as amended for S-2 and S-3; ADR-0004 *Migrations*, "Refuse").

Each container's whole log is read, as `docker logs` returns it: Alembic's own error print and
the interpreter's default exception hook write there, past the application's logging.

Cases: (1) a test-only revision fails on a statement whose bound parameter is a marker; (2) the
connection is refused for a wrong password; (3) the database host does not resolve. (2) and (3)
also run for `backend`'s and `worker`'s start-up. Further: a failure inside `create_app()` in a
uvicorn worker process (S-2), uvicorn's own factory-load record for a `TypeError` (Q-5 A), and a
settings value Pydantic would echo. Contrast: the same failing revision with `env.py`'s handling
replaced by Alembic's plain logging puts the traceback text, `[SQL` and the marker in the log.
"""

import re
import secrets
import subprocess
import time

import pytest

from tests.runtime.eko113 import backend_as, container_log, fixture_image, serve_command
from tests.runtime.lab import Lab, configuration_values, docker
from tests.support import log_lines as ll
from tests.support.fixture_app import DRIVER_URL
from tests.support.fixture_app import MARKER as FIXTURE_MARKER

pytestmark = pytest.mark.runtime

REVISION_MARKER = "marker-k05-e113rev"
TOKEN = secrets.token_hex(5)
WRONG_SECRET = f"wrong-pw-{TOKEN}"
UNREACHABLE = f"db-{TOKEN}.invalid"
HANDLING = (
    '    install_process_logging("migrate")\n    try:\n        dispatch()\n    except Exception:\n'
)
PLAIN = (
    "    import logging as plain\n    plain.basicConfig()\n    try:\n        dispatch()\n"
    "    except ZeroDivisionError:\n"
)


def forbidden(lab: Lab, *extra: str) -> list[str]:
    return [REVISION_MARKER, "[SQL", "[parameters", "Traceback", "postgresql+psycopg",
            *configuration_values(lab), *extra]  # fmt: skip


def error_line_problems(text: str, process: str) -> list[str]:
    """At least one error line of `process`, and every JSON line in the documented form."""
    lines, _ = ll.json_lines(text)
    problems = [p for line in lines for p in ll.app_line_problems(line)]
    errors = [line for line in lines if line.get("event") == "error"]
    if not errors:
        problems.append(f"no error line in {text[-1500:]!r}")
    for line in errors:
        if line.get("process") != process or "correlation_id" in line:
            problems.append(f"error line {line}")
    return problems


def run_service(
    lab: Lab, service: str, *env: tuple[str, str], timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    """One run of the service's own command, with variables overridden as an operator would."""
    args = ["run", "--rm", "--no-deps"]
    for name, value in env:
        args += ["-e", f"{name}={value}"]
    return lab.composition.compose(*args, service, check=False, timeout=timeout)


def test_adr0005_uncaught_driver_error_failing_revision(lab: Lab) -> None:
    lab.reset()
    image = lab.variant("eko113_marker", ("t_eko113_marker.py",))
    code, logs = lab.run_migrate(image)
    assert code != 0, logs
    assert error_line_problems(logs, "migrate") == []
    [line] = [x for x in ll.json_lines(logs)[0] if x.get("event") == "error"]
    assert line["error"] == "sqlalchemy.exc.DataError"
    assert line["cause"] == "psycopg.errors.InvalidTextRepresentation"
    assert line["at"].startswith("migrations/versions/t_eko113_marker.py:upgrade:"), line
    assert ll.leaks(logs, *forbidden(lab)) == []


def test_adr0005_uncaught_driver_error_contrast_without_env_py_handling(lab: Lab) -> None:
    lab.reset()
    image = lab.planted_env_py("eko113_plain", HANDLING, PLAIN, ("t_eko113_marker.py",))
    code, logs = lab.run_migrate(image)
    assert code != 0
    assert REVISION_MARKER in logs
    assert "[SQL" in logs and "[parameters" in logs


CONNECTION_CASES = {
    "wrong-password": (("APP_DB_PASSWORD", WRONG_SECRET),),
    "unreachable-host": (("APP_DB_HOST", UNREACHABLE),),
}


@pytest.mark.parametrize("service", ["migrate", "backend", "worker"])
@pytest.mark.parametrize("case", sorted(CONNECTION_CASES))
def test_adr0005_uncaught_driver_error_connection_refused(
    lab: Lab, service: str, case: str
) -> None:
    lab.at_head()
    result = run_service(lab, service, *CONNECTION_CASES[case])
    text = result.stdout + result.stderr
    assert result.returncode != 0, text[-2000:]
    assert error_line_problems(text, service) == []
    assert ll.leaks(text, *forbidden(lab, WRONG_SECRET, UNREACHABLE)) == []
    if service != "migrate":
        # The error line, then EKO-1-11's refusal line, unchanged.
        assert f"{service} refused to start: the database revision could not be read" in text


@pytest.mark.parametrize("service", ["migrate", "backend", "worker"])
def test_adr0005_uncaught_driver_error_settings_value_not_echoed(lab: Lab, service: str) -> None:
    result = run_service(lab, service, ("APP_DB_PORT", f"marker-port-{TOKEN}"))
    text = result.stdout + result.stderr
    assert result.returncode != 0
    assert "configuration error: missing, empty or invalid environment variable(s): " in text
    assert "APP_DB_PORT" in text
    assert ll.leaks(text, TOKEN, *configuration_values(lab)) == []


@pytest.mark.parametrize(
    ("factory", "error", "at"),
    [
        ("create_broken", "builtins.RuntimeError", "app.main:create_app:"),
        ("create_type_error", "builtins.TypeError", ""),
    ],
)
def test_adr0005_uncaught_driver_error_uvicorn_worker_start(
    lab: Lab, factory: str, error: str, at: str
) -> None:
    """S-2 and Q-5 A: a factory failing inside uvicorn's worker processes."""
    lab.at_head()
    served = backend_as(lab, fixture_image(lab), serve_command(factory))
    try:
        served.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
        container = served.container_id("backend")
        time.sleep(15)
        text = container_log(container)
    finally:
        docker("rm", "-f", served.container_id("backend"), check=False)
        lab.composition.compose("up", "-d", "--no-deps", "--force-recreate", "backend", check=False)
    assert error_line_problems(text, "backend") == []
    errors = [x for x in ll.json_lines(text)[0] if x.get("event") == "error"]
    assert {x["error"] for x in errors} == {error}, errors
    assert all(x["at"].startswith(at) for x in errors), errors
    assert ll.leaks(text, FIXTURE_MARKER, DRIVER_URL, "Traceback", *configuration_values(lab)) == []
    assert not re.search(r"^\s+File \"", text, re.MULTILINE)
