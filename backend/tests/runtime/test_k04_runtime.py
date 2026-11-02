"""K-04 runtime controls: ADR-0001-C7, the OpenAPI half of ADR-0003-C23, ADR-0004-C10 and C28."""

import json
import subprocess
import time
from typing import Any

import pytest

from tests.runtime.backup_lab import BackupLab, SessionSampler
from tests.runtime.conftest import Composition, Started, read_env, write_env
from tests.runtime.test_k04_c28_failed_first_init import databases_on_volume
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
INIT_STOP_SECONDS = 120


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


def wait_for_exit(container: str, seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{json .State}}", container],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        state = json.loads(out)
        if state["Status"] == "exited":
            break
        time.sleep(2)
    return state


def test_k04_c28_empty_role_password_stops_first_init_and_creates_neither_database(
    fresh: Composition,
) -> None:
    # Detached and polled (QA): run in the foreground, an init that does not stop never returns,
    # and the test hung instead of failing on its assertion.
    started = fresh.compose("run", "-d", "--no-deps", "-e", f"{EMPTIED}=", "postgres", timeout=300)
    container = started.stdout.strip().splitlines()[-1]
    try:
        state = wait_for_exit(container, INIT_STOP_SECONDS)
        logs = subprocess.run(
            ["docker", "logs", container], capture_output=True, text=True, encoding="utf-8"
        )
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    assert state["Status"] == "exited", "the first initialisation did not stop"
    assert state["ExitCode"] != 0
    assert EMPTIED in logs.stdout + logs.stderr
    # The composition never starts this volume again (ADR-0004-C28 addendum; test in
    # test_k04_c28_failed_first_init.py), so its catalog is read with the plain image.
    databases = databases_on_volume(f"{fresh.project}_pgdata", fresh.env["POSTGRES_PASSWORD"])
    assert {"eko", "keycloak"} & databases == set()


def test_k04_c28_contrast_with_every_password_set_both_databases_exist(running: Started) -> None:
    databases = {row[0] for row in running.composition.sql("SELECT datname FROM pg_database")}
    assert {"eko", "keycloak"} <= databases


# ADR-0004-C10 for backup's four variables (EKO-1-14 K-06): refused before any connection -------

BACKUP_VARIABLES = (
    "BACKUP_DESTINATION_CREDENTIAL",
    "BACKUP_ENCRYPTION_PUBLIC_KEY",
    "BACKUP_DESTINATION",
    "BACKUP_DESTINATION_HOST_KEY",
)


@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "whitespace"])
@pytest.mark.parametrize("variable", BACKUP_VARIABLES)
def test_k06_c10_empty_backup_variable_stops_backup_before_it_connects(
    backup_lab: BackupLab, variable: str, value: str
) -> None:
    logged = backup_lab.connections_logged()
    attempts = len(backup_lab.double.records())
    with SessionSampler(backup_lab.composition) as sampler:
        result = backup_lab.run(env={variable: value})
    assert result.code != 0
    refusal = f"configuration error: missing or empty environment variable: {variable}"
    assert refusal in result.stderr
    assert sampler.maximum == 0
    assert backup_lab.connections_logged() == logged
    assert len(backup_lab.double.records()) == attempts


@pytest.mark.parametrize("variable", BACKUP_VARIABLES)
def test_k06_c10_unset_backup_variable_stops_the_composition_naming_it(
    backup_lab: BackupLab, variable: str
) -> None:
    composition = backup_lab.composition
    values = read_env(composition.env_file)
    del values[variable]
    unset_env = composition.env_file.parent / f"unset-{variable}.env"
    write_env(unset_env, values)
    unset = Composition(project=composition.project + "-unset", env_file=unset_env)
    try:
        result = unset.compose("up", "--no-build", "-d", "backup", check=False, timeout=180)
        assert result.returncode != 0
        assert variable in result.stderr
        assert unset.compose("ps", "-a", "-q", check=False).stdout.split() == []
    finally:
        unset.down()


def test_k06_c10_contrast_with_every_variable_set_backup_connects_and_reaches_the_double(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    logged = backup_lab.connections_logged()
    attempts = len(backup_lab.double.records())
    with SessionSampler(backup_lab.composition) as sampler:
        result = backup_lab.run()
    assert result.code == 0, result.stderr
    assert sampler.maximum > 0
    assert backup_lab.connections_logged() > logged
    assert len(backup_lab.double.records()) > attempts
