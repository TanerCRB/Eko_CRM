"""K-01 / ADR-0003-C23 health half, the parts provable without a database: the failure answer."""

from fastapi.testclient import TestClient

from tests.unit.conftest import SYNTHETIC_PASSWORD

HEALTH = "/api/health"


def test_k01_health_get_answers_503_status_only_when_database_unreachable(
    client: TestClient,
) -> None:
    response = client.get(HEALTH)
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["content-type"].startswith("application/json")


def test_k01_health_failure_body_holds_no_error_text_or_configuration(client: TestClient) -> None:
    body = client.get(HEALTH).text
    for leak in (SYNTHETIC_PASSWORD, "127.0.0.1", "psycopg", "Error", "eko_app", "alembic"):
        assert leak not in body


def test_k01_health_head_answers_503_when_database_unreachable(client: TestClient) -> None:
    assert client.head(HEALTH).status_code == 503


def test_k01_health_post_is_not_success(client: TestClient) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, HEALTH)
        assert response.status_code == 405, method


def test_k01_health_needs_no_cookie_and_sets_none(client: TestClient) -> None:
    response = client.get(HEALTH)
    assert response.status_code != 401
    assert "set-cookie" not in response.headers
