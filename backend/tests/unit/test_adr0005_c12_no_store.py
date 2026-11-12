"""EKO-1-13 K-07 (a): every response `backend` sends under `/api/` carries exactly
`Cache-Control: no-store`, set by the outermost layer (ADR-0005 addendum 2026-11-02, G-2 A).

The cases include the responses no per-route code produces: the router's 404, 405 and redirect,
request validation's 422 and the server-error middleware's 500 (raised in a route and in a
middleware). Contrast: an application without the repository's request handling sends none of
them with the header, so the check can fail.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import health
from app.main import create_app
from tests.support.fixture_app import add_fixture_routes

# (method, path, expected status): one case per kind of response.
CASES = [
    ("GET", "/api/health", 200),
    ("GET", "/api/health", 503),
    ("HEAD", "/api/health", 200),
    ("OPTIONS", "/api/health", 405),
    ("POST", "/api/health", 405),
    ("GET", "/api/no-such-route", 404),
    ("GET", "/api", 404),
    ("GET", "/api/health/", 307),
    ("POST", "/api/fixture/body", 422),
    ("GET", "/api/fixture/boom", 500),
    ("GET", "/api/fixture/middleware-boom", 500),
    ("GET", "/api/fixture/cached", 200),
]


def no_store_problems(app: FastAPI, ready: bool, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(health, "is_ready", lambda database: ready)
    problems = []
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as client:
        for method, path, status in CASES:
            if path == "/api/health" and method in {"GET", "HEAD"} and (status == 200) != ready:
                continue
            response = client.request(method, path, json={"name": 1} if "body" in path else None)
            if response.status_code != status:
                problems.append(f"{method} {path}: status {response.status_code}, not {status}")
            values = response.headers.get_list("cache-control")
            if values != ["no-store"]:
                problems.append(f"{method} {path} ({response.status_code}): cache-control {values}")
    return problems


@pytest.fixture
def fixture_app(backend_env: None) -> Iterator[FastAPI]:
    yield add_fixture_routes(create_app())


@pytest.mark.parametrize("ready", [True, False], ids=["health-200", "health-503"])
def test_adr0005_c12_no_store_on_every_api_response(
    fixture_app: FastAPI, monkeypatch: pytest.MonkeyPatch, ready: bool
) -> None:
    assert no_store_problems(fixture_app, ready, monkeypatch) == []


def test_adr0005_c12_no_store_not_claimed_outside_api(fixture_app: FastAPI) -> None:
    """G-2 A claims nothing outside `/api/`; the identifier is still on the response."""
    with TestClient(fixture_app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "eko-correlation-id" in response.headers


def test_adr0005_c12_contrast_an_app_without_the_handling_fails(
    backend_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One element changed: the same routes on an application the handling is not installed on."""
    bare = FastAPI()
    bare.include_router(health.router, prefix="/api")
    bare.state.database = create_app().state.database
    add_fixture_routes(bare)
    problems = no_store_problems(bare, True, monkeypatch)
    assert any("/api/fixture/boom (500): cache-control []" in p for p in problems), problems
    assert any("/api/no-such-route (404): cache-control []" in p for p in problems), problems
