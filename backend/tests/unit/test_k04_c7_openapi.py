"""K-04: ADR-0001-C7 (valid OpenAPI 3.x) and the backend side of ADR-0003-C23."""

from typing import Any

from fastapi.testclient import TestClient

from tests.support.openapi import openapi_3_errors

SWAGGER_2: dict[str, Any] = {
    "swagger": "2.0",
    "info": {"title": "x", "version": "1"},
    "paths": {},
}


def test_k04_c7_openapi_document_is_valid_3x(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert openapi_3_errors(response.json()) == []


def test_k04_c7_check_rejects_an_openapi_2_document() -> None:
    assert openapi_3_errors(SWAGGER_2) != []


def test_k04_c7_check_rejects_a_3x_document_that_does_not_validate() -> None:
    assert openapi_3_errors({"openapi": "3.1.0", "paths": {}}) != []


def test_k04_c23_openapi_and_docs_are_not_served_under_the_api_prefix(client: TestClient) -> None:
    # proxy forwards only /api/ to backend, so nothing under it may describe the API.
    for path in ("/api/openapi.json", "/api/docs", "/api/redoc", "/api/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path


def test_k04_c23_api_prefix_holds_exactly_health_the_four_auth_routes_and_customers(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert sorted(paths) == [
        "/api/auth/callback",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/session",
        "/api/customers",
        "/api/customers/{customer_id}",
        "/api/customers/{customer_id}/archive",
        "/api/customers/{customer_id}/restore",
        "/api/health",
        "/api/reference/voivodeships",
        "/api/reps",
        "/api/visits",
        "/api/visits/period",
        "/api/visits/{visit_id}",
    ]
    # EKO-3-01 (decision H6-B A on Issue #195): the three customer operations; EKO-3-05 (Q-5 on
    # Issue #253) adds edit, archive and restore.
    assert sorted(paths["/api/customers"]) == ["get", "post"]
    assert sorted(paths["/api/customers/{customer_id}"]) == ["get", "put"]
    assert sorted(paths["/api/health"]) == ["get", "head"]
    # EKO-3-02 (Q-3 A on Issue #208): the read-only voivodeship and county reference.
    assert sorted(paths["/api/reference/voivodeships"]) == ["get"]
    # EKO-3-08 (G-4 A on Issue #216): the manager's list of reps.
    assert sorted(paths["/api/reps"]) == ["get"]
    # EKO-4-01 (Issue #268): plan a visit, read it, list all and a period.
    assert sorted(paths["/api/visits"]) == ["get", "post"]
    assert sorted(paths["/api/visits/period"]) == ["get"]
    assert sorted(paths["/api/visits/{visit_id}"]) == ["get"]
