"""EKO-1-13 K-07 (a), through `proxy`: `Cache-Control: no-store` and `Eko-Correlation-Id` set by
`backend` arrive unchanged, on success and on the router's own error responses (ADR-0005
addendum of 2026-11-02: `proxy` sets and strips no `Cache-Control` for `/api/`).

Contrast: a response `proxy` generates itself (its 404 for the OpenAPI path) carries neither, so
the check is not satisfied by `proxy` adding the header.
"""

import secrets

import pytest

from tests.runtime.conftest import Started

pytestmark = pytest.mark.runtime


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/api/health", 200),
        ("HEAD", "/api/health", 200),
        ("POST", "/api/health", 405),
        ("GET", f"/api/eko113-{secrets.token_hex(4)}", 404),
        ("GET", "/api/health/", 307),
    ],
)
def test_adr0005_c12_no_store_through_proxy(
    running: Started, method: str, path: str, status: int
) -> None:
    response = running.composition.through_proxy("app", path, method=method)
    assert response.status_code == status
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert len(response.headers.get_list("eko-correlation-id")) == 1


def test_adr0005_c12_no_store_through_proxy_contrast_proxy_own_response(running: Started) -> None:
    response = running.composition.through_proxy("app", "/openapi.json")
    assert response.status_code == 404
    assert "no-store" not in response.headers.get("cache-control", "")
    assert "eko-correlation-id" not in response.headers
