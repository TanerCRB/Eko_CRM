"""K-04 runtime controls: ADR-0001-C7, the OpenAPI half of ADR-0003-C23, ADR-0004-C10 and C28."""

import json
import subprocess

import pytest

from tests.runtime.conftest import Composition, Started, read_env, write_env
from tests.support.openapi import openapi_3_errors

pytestmark = pytest.mark.runtime

# Service -> (variable the test empties in the container, variable Compose requires).
SECRETS = {
    "backend": ("APP_DB_PASSWORD", "APP_DB_PASSWORD"),
    "migrate": ("APP_DB_PASSWORD", "APP_DB_PASSWORD"),
    "worker": ("APP_DB_PASSWORD", "APP_DB_PASSWORD"),
    "keycloak": ("KC_DB_PASSWORD", "KEYCLOAK_DB_PASSWORD"),
    "backup": ("BACKUP_DB_PASSWORD", "BACKUP_DB_PASSWORD"),
}
OPENAPI_PATHS = [
    "/openapi.json",
    "/docs",
    "/redoc",
    "/docs/oauth2-redirect",
    "/api/openapi.json",
    "/api/docs",
    "/openapi.json/",
    "/docs/",
    "/OpenAPI.JSON",
    "/DOCS",
    "/%6Fpenapi.json",
    "/%64ocs",
    "/api/../openapi.json",
    "/api/%2e%2e/openapi.json",
]
LISTENERS = ["app", "auth", "admin", "http"]
EMPTIED = "KEYCLOAK_DB_PASSWORD"


def holds_openapi_content(body: str) -> bool:
    lowered = body.lower()
    if "swagger-ui" in lowered or "redoc" in lowered:
        return True
    try:
        document = json.loads(body)
    except ValueError:
        return False
    return isinstance(document, dict) and ("openapi" in document or "swagger" in document)


# ADR-0001-C7 ---------------------------------------------------------------------------------


def test_k04_c7_openapi_fetched_from_backend_inside_the_network_is_valid_3x(
    running: Started,
) -> None:
    document = json.loads(running.composition.fetch_in_network("http://backend:8000/openapi.json"))
    assert openapi_3_errors(document) == []


# ADR-0003-C23, OpenAPI half ------------------------------------------------------------------


@pytest.mark.parametrize("listener", LISTENERS)
@pytest.mark.parametrize("path", OPENAPI_PATHS)
def test_k04_c23_no_listener_of_proxy_serves_openapi_content(
    running: Started, listener: str, path: str
) -> None:
    response = running.composition.through_proxy(listener, path)
    assert not holds_openapi_content(response.text), (listener, path, response.status_code)


def test_k04_c23_contrast_backend_directly_serves_the_document_and_docs(running: Started) -> None:
    composition = running.composition
    assert holds_openapi_content(composition.fetch_in_network("http://backend:8000/openapi.json"))
    assert holds_openapi_content(composition.fetch_in_network("http://backend:8000/docs"))


# ADR-0004-C10, AQ-3 A: a secret unset, and a secret empty ---------------------------------------


@pytest.mark.parametrize("service", sorted(SECRETS))
def test_k04_c10_empty_secret_stops_the_service_naming_it(running: Started, service: str) -> None:
    inner, outer = SECRETS[service]
    result = running.composition.compose(
        "run", "--rm", "--no-deps", "-T", "-e", f"{inner}=", service, check=False, timeout=180
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert inner in output or outer in output


@pytest.mark.parametrize("service", sorted(SECRETS))
def test_k04_c10_unset_secret_stops_the_composition_naming_it(
    running: Started, service: str
) -> None:
    _, outer = SECRETS[service]
    values = read_env(running.composition.env_file)
    del values[outer]
    unset_env = running.composition.env_file.parent / f"unset-{outer}.env"
    write_env(unset_env, values)
    unset = Composition(project=running.composition.project + "-unset", env_file=unset_env)
    try:
        result = unset.compose("up", "--no-build", "-d", service, check=False, timeout=180)
        assert result.returncode != 0
        assert outer in result.stderr
        listed = unset.compose("ps", "-a", "-q", check=False).stdout.split()
        assert listed == []
    finally:
        unset.down()


@pytest.mark.parametrize(
    ("image_service", "command"),
    [
        ("backend", []),
        ("migrate", ["alembic", "upgrade", "head"]),
        ("worker", ["python", "-m", "app.worker"]),
        ("backup", []),
    ],
)
def test_k04_c10_image_alone_refuses_to_start_without_its_secret(
    running: Started, image_service: str, command: list[str]
) -> None:
    # By name: `compose run backend` rebuilds the image, so an earlier image ID may be gone.
    image = running.composition.inspect(image_service)["Config"]["Image"]
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", image, *command],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode != 0
    assert "PASSWORD" in result.stderr


# ADR-0004-C28: an empty role password stops the first initialisation ---------------------------


def test_k04_c28_empty_role_password_stops_first_init_and_creates_neither_database(
    fresh: Composition,
) -> None:
    failed = fresh.compose(
        "run", "--rm", "--no-deps", "-T", "-e", f"{EMPTIED}=", "postgres",
        check=False, timeout=300,
    )  # fmt: skip
    assert failed.returncode != 0
    assert EMPTIED in failed.stdout + failed.stderr
    # The same volume started again skips the init content: the databases were never created.
    fresh.compose("up", "--wait", "postgres", timeout=300)
    databases = {row[0] for row in fresh.sql("SELECT datname FROM pg_database", "postgres")}
    assert {"eko", "keycloak"} & databases == set()


def test_k04_c28_contrast_with_every_password_set_both_databases_exist(running: Started) -> None:
    databases = {row[0] for row in running.composition.sql("SELECT datname FROM pg_database")}
    assert {"eko", "keycloak"} <= databases
