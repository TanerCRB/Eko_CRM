"""EKO-1-13 K-04, ADR-0005-C2: a request that fails validation leaves its input in no line the
backend logs, on every route of `create_app()` that accepts a body.

No such route exists yet, so the real-app test says so in its output (a warning naming the count)
and never passes silently on an empty set. Contrast (b): the same enumeration on a fixture app with
one body endpoint finds exactly that endpoint; with the fixture logging the rejected input the
check fails, and with the repository's handling it passes.
"""

import logging
import warnings
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.responses import Response

from app.main import create_app
from tests.support import log_lines as ll
from tests.support.c2_routes import BodyRoute, body_routes, invalid_bodies
from tests.support.fixture_app import (
    LONG_MARKER,
    MARKER,
    NON_ASCII_MARKER,
    add_fixture_routes,
    install_for_test,
)
from tests.support.fixture_app import restored_process_state as restored

Output = Callable[[], str]
# Read at import, before any test installs the repository's printer in this process.
PYTHON_SHOWWARNING = warnings.showwarning
MARKERS = {"plain": MARKER, "non-ascii": NON_ASCII_MARKER, "long": LONG_MARKER}


@pytest.fixture
def output(capfd: pytest.CaptureFixture[str]) -> Iterator[Output]:

    with restored():
        install_for_test("backend")
        capfd.readouterr()
        yield lambda: capfd.readouterr().err


def c2_problems(app: FastAPI, routes: list[BodyRoute], output: Output) -> list[str]:
    problems = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for route in routes:
            for label, marker in MARKERS.items():
                for variant, kwargs in invalid_bodies(route, marker).items():
                    response = client.request(route.method, route.path, **kwargs)
                    text = output()
                    where = f"{route.method} {route.path} {variant}/{label}"
                    if response.status_code != 422:
                        problems.append(f"{where}: status {response.status_code}")
                    lines, others = ll.json_lines(text)
                    requests = [line for line in lines if line.get("event") == "request"]
                    if len(requests) != 1 or others:
                        problems.append(f"{where}: lines {lines} {others}")
                    if ll.leaks(text, marker[:40]):
                        problems.append(f"{where}: the rejected input is in the log")
    return problems


def test_adr0005_c2_validation_input_not_logged_on_every_body_route(
    backend_env: None, output: Output
) -> None:
    app = create_app()
    routes = body_routes(app)
    # Through Python's own printer, so pytest records the text: the repository's printer, which
    # create_app() installs, writes a warning's category only (ADR-0005 amendment, S-5).
    installed, warnings.showwarning = warnings.showwarning, PYTHON_SHOWWARNING
    try:
        warnings.warn(
            f"ADR-0005-C2: create_app() declares {len(routes)} route(s) that accept a body"
            + (
                "; the check is vacuous until the first one (EKO-2-01 or later)"
                if not routes
                else ""
            ),
            stacklevel=1,
        )
    finally:
        warnings.showwarning = installed
    assert c2_problems(app, routes, output) == []


def test_adr0005_c2_contrast_enumeration_finds_the_fixture_endpoint(backend_env: None) -> None:
    routes = body_routes(add_fixture_routes(create_app()))
    assert routes == [BodyRoute("POST", "/api/fixture/body", ("name", "count", "inner"))]


def test_adr0005_c2_contrast_repository_handling_passes(backend_env: None, output: Output) -> None:
    app = add_fixture_routes(create_app())
    assert c2_problems(app, body_routes(app), output) == []


def test_adr0005_c2_contrast_a_handler_logging_the_input_fails(
    backend_env: None, output: Output
) -> None:
    """Planted: a validation handler that logs what was rejected, through the app's logger."""
    app = add_fixture_routes(create_app())

    async def logging_handler(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RequestValidationError)
        logging.getLogger("app.fixture").warning("rejected %s", exc.errors())
        return await request_validation_exception_handler(request, exc)

    app.add_exception_handler(RequestValidationError, logging_handler)
    problems = c2_problems(app, body_routes(app), output)
    assert any("the rejected input is in the log" in p for p in problems), problems
