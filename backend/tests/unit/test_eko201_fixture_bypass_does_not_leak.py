"""EKO-2-01, human decision H6-2 A (#21): the fixture app bypasses the access dependency; the
shipped `create_app()` does not, so the bypass cannot leak into what ships."""

from fastapi.testclient import TestClient

from app.auth.gate import authenticate
from app.main import create_app
from tests.support.fixture_app import add_fixture_routes, create


def test_eko201_create_app_carries_no_dependency_override(backend_env: None) -> None:
    app = create_app()
    assert app.dependency_overrides == {}
    # Contrast: an unauthenticated call on a protected route is refused by the real dependency.
    with TestClient(app) as client:
        assert client.get("/api/auth/session").status_code == 401


def test_eko201_fixture_app_bypasses_only_the_access_dependency(backend_env: None) -> None:
    app = add_fixture_routes(create_app())
    assert set(app.dependency_overrides) == {authenticate}


def test_eko201_runtime_fixture_factory_gets_the_same_bypass(backend_env: None) -> None:
    assert set(create().dependency_overrides) == {authenticate}
