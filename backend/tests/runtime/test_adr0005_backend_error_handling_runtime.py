"""EKO-1-13 K-04, runtime half: the fixture app under the backend's real process entry and
logging configuration. It runs in a test variant image built `FROM` the shipped image that only
adds the fixture module; its command calls the shipped `serve.main` with the fixture's factory, so
the settings check, the revision check, `log_config`, `access_log=False` and the worker count are
the ones that ship (ADR-0005 addendum of 2026-11-02, *Under `serve.py`'s process configuration*).

Contrast (a): the same routes on an application without the repository's handling, served by
uvicorn's defaults (one element changed), put the traceback and the marker in the output.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest

from tests.runtime.eko113 import (
    Window,
    backend_as,
    fixture_image,
    get_in_network,
    restore_backend,
    serve_command,
    wait_for_status,
)
from tests.runtime.lab import Lab, configuration_values
from tests.support import log_lines as ll
from tests.support.fixture_app import FORBIDDEN, FORBIDDEN_TEXT, MARKER

pytestmark = pytest.mark.runtime

BASE = "http://backend:8000"
ERRORS = {
    "/api/fixture/boom": "builtins.RuntimeError",
    "/api/fixture/driver": "sqlalchemy.exc.OperationalError",
    "/api/fixture/real-driver": "sqlalchemy.exc.DataError",
    "/api/fixture/group": "builtins.ExceptionGroup",
    "/api/fixture/long": "builtins.RuntimeError",
    "/api/fixture/middleware-boom": "builtins.RuntimeError",
}


@pytest.fixture(scope="module")
def fixture_backend(lab: Lab) -> Iterator[Window]:
    lab.at_head()
    served = backend_as(lab, fixture_image(lab), serve_command("create"))
    try:
        served.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
        wait_for_status(lab, f"{BASE}/api/health", 200)
        yield Window(served.container_id("backend"), 0)
    finally:
        restore_backend(lab)


def forbidden(lab: Lab) -> list[str]:
    return [*FORBIDDEN, *FORBIDDEN_TEXT, *configuration_values(lab)]


@pytest.mark.parametrize("path", sorted(ERRORS))
def test_adr0005_backend_error_handling_runtime(
    lab: Lab, fixture_backend: Window, path: str
) -> None:
    response = get_in_network(lab, f"{BASE}{path}?q={MARKER}")
    text = fixture_backend.text()
    assert response["status"] == 500
    assert response["body"] == "Internal Server Error"
    cid = response["headers"]["eko-correlation-id"]
    lines, others = ll.json_lines(text)
    assert others == [], others[:5]
    mine = [line for line in lines if line.get("correlation_id") == cid]
    assert [line["event"] for line in mine] == ["error", "request"], mine
    assert mine[0]["error"] == ERRORS[path]
    assert ll.app_line_problems(mine[0]) == []
    assert ll.leaks(text + json.dumps(response), *forbidden(lab)) == []


def test_adr0005_backend_error_handling_runtime_rejected_body(
    lab: Lab, fixture_backend: Window
) -> None:
    body = json.dumps({"name": {"v": MARKER}, "count": MARKER, "inner": MARKER, "extra": MARKER})
    response = get_in_network(
        lab, f"{BASE}/api/fixture/body", {"Content-Type": "application/json"}, body
    )
    assert response["status"] == 422
    text = fixture_backend.text()
    assert ll.leaks(text, *forbidden(lab)) == []


def test_adr0005_backend_error_handling_runtime_pool_record(
    lab: Lab, fixture_backend: Window
) -> None:
    response = get_in_network(lab, f"{BASE}/api/fixture/pool")
    assert response["status"] == 200
    lines, _ = ll.json_lines(fixture_backend.text())
    pool: list[dict[str, Any]] = [line for line in lines if line["logger"].startswith("sqlalchemy")]
    assert pool and all(line["event"] == "error" for line in pool), pool
    assert ll.leaks(json.dumps(lines), *forbidden(lab)) == []


def test_adr0005_backend_error_handling_runtime_contrast_without_the_handling(lab: Lab) -> None:
    command = ["python", "-c", "import uvicorn; uvicorn.run('eko113_fixture_app:bare', "
               "factory=True, host='0.0.0.0', port=8000)"]  # fmt: skip
    planted = backend_as(lab, fixture_image(lab), command)
    try:
        planted.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
        wait_for_status(lab, f"{BASE}/api/fixture/log-sync", 200)
        get_in_network(lab, f"{BASE}/api/fixture/boom")
        text = Window(planted.container_id("backend"), 0).text()
    finally:
        restore_backend(lab)
    assert "Traceback" in text
    assert MARKER in text
