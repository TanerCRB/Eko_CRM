"""EKO-1-13 K-03, unit complement of the runtime files: the identifier and the request line as
`create_app()` and the process logging install them, in one process.

The runtime files are the proof on the shipped process (both uvicorn workers, through `proxy`);
these pin the same rules close to the code: one identifier per request from no client value, on
every response in `Eko-Correlation-Id`, on every line written while the request is handled
(a route's thread and two concurrent requests included), and one request line per request.
"""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import anyio
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from tests.support import log_lines as ll
from tests.support.fixture_app import MARKER, NON_ASCII_MARKER, add_fixture_routes, install_for_test
from tests.support.fixture_app import restored_process_state as restored

CLIENT_HEADERS = {
    "X-Request-ID": f"{MARKER}-xrid",
    "X-Correlation-ID": f"{MARKER}-xcid",
    "traceparent": f"00-{'a' * 32}-{'b' * 16}-01",
    "Eko-Correlation-Id": "c" * 32,
}


@pytest.fixture
def output(capfd: pytest.CaptureFixture[str]) -> Iterator[Callable[[], list[dict[str, Any]]]]:

    with restored():
        install_for_test("backend")
        capfd.readouterr()

        def lines() -> list[dict[str, Any]]:
            parsed, _ = ll.json_lines(capfd.readouterr().err)
            return parsed

        yield lines


@pytest.fixture
def app(backend_env: None) -> FastAPI:
    return add_fixture_routes(create_app())


def request_lines(lines: list[dict[str, Any]], cid: str) -> list[dict[str, Any]]:
    return [line for line in lines if line.get("event") == "request" and line.get(
        "correlation_id") == cid]  # fmt: skip


def test_adr0005_correlation_identifier_on_every_response_and_line(
    app: FastAPI, output: Callable[[], list[dict[str, Any]]]
) -> None:
    with TestClient(app) as client:
        response = client.get("/api/fixture/log-sync", headers=CLIENT_HEADERS)
    cid = response.headers["eko-correlation-id"]
    assert ll.CORRELATION_ID.fullmatch(cid), cid
    assert cid not in CLIENT_HEADERS.values()
    lines = output()
    mine = [line for line in lines if line.get("correlation_id") == cid]
    # The route's own line, written in the thread pool, and the request line.
    assert [line["event"] for line in mine] == ["message", "request"], lines
    assert mine[0]["msg"] == "fixture line from a thread"
    assert [ll.app_line_problems(line) for line in lines] == [[] for _ in lines]
    assert ll.leaks(str(lines), MARKER) == []


def test_adr0005_correlation_identifier_contrast_two_requests_differ(
    app: FastAPI, output: Callable[[], list[dict[str, Any]]]
) -> None:
    with TestClient(app) as client:
        first = client.get("/api/fixture/log-sync", headers=CLIENT_HEADERS)
        second = client.get("/api/fixture/log-sync", headers=CLIENT_HEADERS)
    assert first.headers["eko-correlation-id"] != second.headers["eko-correlation-id"]


def test_adr0005_correlation_identifier_concurrent_requests_keep_their_own(
    app: FastAPI, output: Callable[[], list[dict[str, Any]]]
) -> None:
    async def both() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            results: list[httpx.Response] = []

            async def one() -> None:
                results.append(await client.get("/api/fixture/log-async"))

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(one)
                tasks.start_soon(one)
            return results

    responses = anyio.run(both)
    lines = output()
    ids = {r.headers["eko-correlation-id"] for r in responses}
    assert len(ids) == 2
    for cid in ids:
        mine = [line.get("msg", line.get("event")) for line in lines if line.get(
            "correlation_id") == cid]  # fmt: skip
        assert mine == ["fixture line before the pause", "fixture line after the pause",
                        "request"], lines  # fmt: skip


@pytest.mark.parametrize(
    ("method", "path", "status", "route"),
    [
        ("GET", "/api/health", 503, "/api/health"),
        ("HEAD", "/api/health", 503, "/api/health"),
        ("POST", "/api/health", 405, "/api/health"),
        ("GET", f"/api/{MARKER}", 404, "/api/*"),
        ("GET", f"/api/health/{MARKER}/{'0f' * 4}-aaaa-bbbb-cccc-{'d' * 12}", 404,
         f"/api/health/*/{'0f' * 4}-aaaa-bbbb-cccc-{'d' * 12}"),
        ("GET", "/api/health/", 307, "/api/health/"),
        ("GET", "/openapi.json", 200, "/openapi.json"),
        ("PROPFIND", "/api/health", 405, "/api/health"),
        ("GET", "/api/fixture/boom", 500, "/api/fixture/boom"),
    ],
)  # fmt: skip
def test_adr0005_backend_request_line_unit(
    app: FastAPI,
    output: Callable[[], list[dict[str, Any]]],
    method: str,
    path: str,
    status: int,
    route: str,
) -> None:
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as client:
        response = client.request(
            method,
            f"{path}?q={MARKER}",
            headers={"X-Probe": NON_ASCII_MARKER.encode(), "Cookie": f"sid={MARKER}".encode()},
        )
    assert response.status_code == status
    cid = response.headers["eko-correlation-id"]
    lines = output()
    [line] = request_lines(lines, cid)
    assert line["method"] == ("OTHER" if method == "PROPFIND" else method)
    assert line["route"] == route
    assert line["status"] == status
    assert isinstance(line["duration_ms"], int | float) and line["duration_ms"] >= 0
    assert ll.app_line_problems(line) == []
    assert ll.leaks(str(lines), MARKER, NON_ASCII_MARKER) == []


def test_adr0005_correlation_identifier_cleared_after_the_request(
    app: FastAPI, output: Callable[[], list[dict[str, Any]]]
) -> None:
    """In-task transport: the application runs in the caller's context, so an identifier that is
    not cleared would still be bound when the caller logs next."""

    async def request_then_log() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            await client.get("/api/fixture/log-async")
        logging.getLogger("app.fixture").warning("after the request")

    anyio.run(request_then_log)
    after = [line for line in output() if line.get("msg") == "after the request"]
    assert len(after) == 1, after
    assert "correlation_id" not in after[0]
