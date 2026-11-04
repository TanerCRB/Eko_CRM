"""EKO-1-13 K-03, request line: every request the composition's `backend` (two uvicorn workers)
handles writes exactly one line of the allowed fields, in the form docs/operations/log-format.md
documents; no query, header, cookie or body value reaches it (ADR-0005 addendum of 2026-11-02,
*The request line*, *Lines of other libraries*, G-6 A).

The whole process output is read (`docker logs`: both workers, uvicorn's loggers included), never
captured records. Contrast (b): the same request against the shipped image with uvicorn's access
log switched on under uvicorn's own logging configuration puts the query marker in the output.
Under the repository's `log_config` that switch alone writes nothing (uvicorn's access logger is
below its level, and a third-party line is its format string only, Q-5 A): the unit check on
`serve.main`'s arguments is what fails when it is switched on.
"""

import json
import secrets
import time
from typing import Any

import pytest

from tests.runtime.conftest import Started
from tests.runtime.eko113 import (
    Window,
    backend_as,
    get_in_network,
    json_result,
    python_in_service,
    restore_backend,
    wait_for_status,
    window,
)
from tests.runtime.lab import Lab
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
MARKER = f"marker-rl-{TOKEN}"
NON_ASCII = f"Zażółć-rl-{TOKEN}"

DIRECT = """
import http.client, json, sys
out = []
for method, path, headers in json.loads(REQUESTS):
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=10)
    connection.putrequest(method, path, skip_accept_encoding=True)
    for name, value in headers:
        connection.putheader(name, value.encode("utf-8"))
    connection.endheaders(b"" if method in ("GET", "HEAD") else b'{"x": "BODY"}')
    response = connection.getresponse()
    response.read()
    out.append([method, path, response.status, response.getheader("eko-correlation-id")])
    connection.close()
print(json.dumps({"responses": out}))  # leftovers-allow: container probe; stdout is its answer
"""


def direct(started: Started, requests: list[tuple[str, str, list[tuple[str, str]]]]) -> list[Any]:
    script = DIRECT.replace("REQUESTS", repr(json.dumps(requests))).replace("BODY", MARKER)
    responses: list[Any] = json_result(python_in_service(started.composition, "backend", script))[
        "responses"
    ]
    return responses


def lines_of(text: str) -> list[dict[str, Any]]:
    objects, others = ll.json_lines(text)
    assert others == [], others[:5]
    return objects


MARKED = [("X-Probe", MARKER), ("Cookie", f"sid={MARKER}"), ("X-Other", NON_ASCII)]

CASES = [
    ("GET", "/api/health", 200, "/api/health"),
    ("HEAD", "/api/health", 200, "/api/health"),
    ("POST", "/api/health", 405, "/api/health"),
    ("GET", f"/api/{MARKER}", 404, "/api/*"),
    ("GET", "/api/health/", 307, "/api/health/"),
    ("GET", "/openapi.json", 200, "/openapi.json"),
    ("BREW", "/api/health", 405, "/api/health"),
]


def test_adr0005_backend_request_log_line(running: Started) -> None:
    mark = window(running.composition, "backend")
    requests = [(m, f"{p}?q={MARKER}", MARKED) for m, p, _, _ in CASES]
    responses = direct(running, requests)
    lines = lines_of(mark.text(settle=1.5))
    for (method, _, status, route), (_, _, got, cid) in zip(CASES, responses, strict=True):
        assert got == status, (method, route, got)
        assert ll.CORRELATION_ID.fullmatch(cid or ""), cid
        mine = [line for line in lines if line.get("correlation_id") == cid]
        [line] = [m for m in mine if m["event"] == "request"]
        assert line["method"] == ("OTHER" if method == "BREW" else method)
        assert (line["route"], line["status"], line["process"]) == (route, status, "backend")
        assert ll.app_line_problems(line) == []
    assert [ll.app_line_problems(line) for line in lines] == [[] for _ in lines]
    assert ll.leaks(json.dumps(lines), MARKER, NON_ASCII) == []


def test_adr0005_backend_request_log_line_through_proxy(running: Started) -> None:
    mark = window(running.composition, "backend")
    response = running.composition.through_proxy(
        "app", f"/api/health?q={MARKER}", headers={"X-Probe": MARKER, "Cookie": f"sid={MARKER}"}
    )
    assert response.status_code == 200
    cid = response.headers["eko-correlation-id"]
    lines = lines_of(mark.text())
    assert [(line["route"], line["status"]) for line in lines if line.get("correlation_id") == cid
            and line["event"] == "request"] == [("/api/health", 200)]  # fmt: skip
    assert ll.leaks(json.dumps(lines), MARKER) == []


def test_adr0005_backend_request_log_line_healthcheck_writes_lines(running: Started) -> None:
    """G-6 A: the container healthcheck (every 5 s) writes request lines like any request."""
    mark = window(running.composition, "backend")
    lines = lines_of(mark.text(settle=12))
    health = [line for line in lines if line.get("event") == "request" and
              line.get("route") == "/api/health"]  # fmt: skip
    assert len(health) >= 2, lines


def test_adr0005_backend_request_log_line_websocket_upgrade(running: Started) -> None:
    """Q-5 A edge: an upgrade request with a query marker. The image ships no WebSocket library,
    so uvicorn answers it as plain HTTP and writes only fixed warnings; no line holds the marker."""
    mark = window(running.composition, "backend")
    response = running.composition.through_proxy(
        "app",
        f"/api/{MARKER}?q={MARKER}",
        headers={
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        },  # fmt: skip
    )
    assert response.status_code in {400, 404, 426}, response.status_code
    lines = lines_of(mark.text())
    assert lines, "the upgrade request wrote no line"
    assert ll.leaks(json.dumps(lines), MARKER) == []


def test_adr0005_backend_request_log_line_contrast_uvicorn_access_log_on(lab: Lab) -> None:
    """Planted: the shipped image's uvicorn with its access log on under its own logging."""
    command = ["python", "-c", "import uvicorn; uvicorn.run('app.main:create_app', factory=True, "
               "host='0.0.0.0', port=8000, access_log=True)"]  # fmt: skip
    planted = backend_as(lab, lab.shipped_image, command)
    try:
        planted.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
        wait_for_status(lab, "http://backend:8000/openapi.json", 200)
        mark = Window(planted.container_id("backend"), 0)
        get_in_network(lab, f"http://backend:8000/api/health?q={MARKER}")
        time.sleep(1)
        assert ll.leaks(mark.text(), MARKER) != []
    finally:
        restore_backend(lab)
