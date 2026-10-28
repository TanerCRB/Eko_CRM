"""K-03: postgres initialised as ADR-0004-C28 requires; ADR-0003-C11 and C19 on the live server."""

import json
from pathlib import Path

import pytest

from tests.runtime.conftest import Started
from tests.support import db_checks as dc

pytestmark = pytest.mark.runtime

DEFAULT_ACL_FIXTURE_DB = "k03_default_acl_fixture"


def test_k03_pgdata_is_the_only_mount_of_postgres(running: Started) -> None:
    composition = running.composition
    mounts = composition.inspect("postgres")["Mounts"]
    assert [(m["Type"], m["Name"]) for m in mounts] == [("volume", f"{composition.project}_pgdata")]


def test_k03_three_non_privileged_roles_each_limited(running: Started) -> None:
    rows = running.composition.sql(
        "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolconnlimit FROM pg_roles "
        "WHERE rolname IN ('eko_app', 'eko_keycloak', 'eko_backup')"
    )
    roles = {r[0]: dc.Role(r[0], r[1] == "t", r[2] == "t", r[3] == "t", int(r[4])) for r in rows}
    assert dc.role_violations(roles) == []


def public_can_connect(started: Started, databases: tuple[str, ...]) -> dict[str, bool]:
    rows = started.composition.sql(
        "SELECT datname, has_database_privilege('public', datname, 'CONNECT') FROM pg_database",
        "postgres",
    )
    return {r[0]: r[1] == "t" for r in rows if r[0] in databases}


def test_k03_public_cannot_connect_to_either_database(running: Started) -> None:
    assert dc.public_connect_violations(public_can_connect(running, dc.DATABASES)) == []


def test_k03_contrast_a_database_with_default_privileges_grants_public(running: Started) -> None:
    composition = running.composition
    composition.sql(f"CREATE DATABASE {DEFAULT_ACL_FIXTURE_DB}", "postgres")
    try:
        rows = composition.sql("SELECT datname, datacl IS NULL FROM pg_database", "postgres")
        assert [r[1] for r in rows if r[0] == DEFAULT_ACL_FIXTURE_DB] == ["t"]
        found = public_can_connect(running, (DEFAULT_ACL_FIXTURE_DB,))
        assert found == {DEFAULT_ACL_FIXTURE_DB: True}
    finally:
        composition.sql(f"DROP DATABASE {DEFAULT_ACL_FIXTURE_DB}", "postgres")


WIRE_CLIENT = (Path(__file__).parents[1] / "support" / "pg_connect_sqlstate.py").read_text(
    encoding="utf-8"
)


def connect_results(started: Started, cases: list[tuple[str, str, str]]) -> list[str]:
    """SQLSTATE of each connection attempt, read from the server's ErrorResponse, or "ok"."""
    wire_cases = [("postgres", role, password, database) for role, password, database in cases]
    # The synthetic passwords travel inside the script on stdin, never on a command line.
    script = f"cases = {wire_cases!r}\n{WIRE_CLIENT}"
    result = started.composition.python_in_backend(script)
    assert result.returncode == 0, result.stderr[-2000:]
    found: list[str] = json.loads(result.stdout)
    return found


def test_k03_adr0003_c11_neither_role_connects_to_the_others_database(running: Started) -> None:
    env = running.composition.env
    app, keycloak = env["APP_DB_PASSWORD"], env["KEYCLOAK_DB_PASSWORD"]
    results = connect_results(
        running, [("eko_app", app, "keycloak"), ("eko_keycloak", keycloak, "eko")]
    )
    # 42501 insufficient_privilege: a refusal by privilege, not 28P01 or 3D000.
    assert results == ["42501", "42501"]


def test_k03_contrast_each_role_connects_to_its_own_database(running: Started) -> None:
    env = running.composition.env
    results = connect_results(
        running,
        [
            ("eko_app", env["APP_DB_PASSWORD"], "eko"),
            ("eko_keycloak", env["KEYCLOAK_DB_PASSWORD"], "keycloak"),
            ("eko_backup", env["BACKUP_DB_PASSWORD"], "eko"),
            ("eko_backup", env["BACKUP_DB_PASSWORD"], "keycloak"),
        ],
    )
    assert results == ["ok", "ok", "ok", "ok"]


def test_k03_contrast_wrong_password_and_missing_database_are_other_refusals(
    running: Started,
) -> None:
    env = running.composition.env
    results = connect_results(
        running,
        [("eko_app", "not-the-password", "keycloak"), ("eko_app", env["APP_DB_PASSWORD"], "nodb")],
    )
    assert results == ["28P01", "3D000"]


def test_k03_c19_budget_holds_on_the_values_the_containers_received(running: Started) -> None:
    composition = running.composition
    limits = {
        r[0]: int(r[1])
        for r in composition.sql(
            "SELECT rolname, rolconnlimit FROM pg_roles "
            "WHERE rolname IN ('eko_app', 'eko_keycloak', 'eko_backup')"
        )
    }
    [[max_connections]] = composition.sql("SHOW max_connections")
    [[reserved]] = composition.sql("SHOW superuser_reserved_connections")
    backend = composition.container_env("backend")
    worker = composition.container_env("worker")
    keycloak = composition.container_env("keycloak")
    budget = dc.Budget(
        app_limit=limits["eko_app"],
        keycloak_limit=limits["eko_keycloak"],
        backup_limit=limits["eko_backup"],
        keycloak_pool_max=int(keycloak["KC_DB_POOL_MAX_SIZE"]),
        web_workers=int(backend["WEB_CONCURRENCY"]),
        web_pool_size=int(backend["APP_DB_POOL_SIZE"]),
        web_max_overflow=int(backend["APP_DB_MAX_OVERFLOW"]),
        worker_pool_size=int(worker["APP_DB_POOL_SIZE"]),
        worker_max_overflow=int(worker["APP_DB_MAX_OVERFLOW"]),
        max_connections=int(max_connections),
        superuser_reserved=int(reserved),
    )
    assert dc.c19_violations(budget) == []
