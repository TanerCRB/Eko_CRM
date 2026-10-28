"""K-02 and K-03 checks on values read from a running PostgreSQL: each returns its violations."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

ROLES = ("eko_app", "eko_keycloak", "eko_backup")
DATABASES = ("eko", "keycloak")
MIGRATION_CONNECTIONS = 1


def c1_version(server_version_num: int) -> list[str]:
    """ADR-0002-C1: PostgreSQL 18."""
    if 180000 <= server_version_num <= 189999:
        return []
    return [f"server_version_num {server_version_num} is not 18.x"]


def c2_heads(heads_output: str, stamped: Iterable[str]) -> list[str]:
    """ADR-0002-C2: `alembic heads` prints one revision, and alembic_version holds it."""
    heads = [line.split()[0] for line in heads_output.splitlines() if line.strip()]
    problems = []
    if len(heads) != 1:
        problems.append(f"alembic heads printed {heads}")
    if sorted(stamped) != sorted(heads[:1]):
        problems.append(f"alembic_version holds {sorted(stamped)}, head is {heads[:1]}")
    return problems


def c5_database(encoding: str, provider: str, locale: str | None) -> list[str]:
    """ADR-0002-C5, encoding and ICU parts: exactly UTF8, 'i' and 'pl-PL'."""
    problems = []
    if encoding != "UTF8":
        problems.append(f"server_encoding {encoding}")
    if provider != "i":
        problems.append(f"datlocprovider {provider!r}")
    if locale != "pl-PL":
        problems.append(f"datlocale {locale!r}")
    return problems


def c6_naive_columns(rows: Iterable[tuple[str, str]]) -> list[str]:
    """ADR-0002-C6: rows of (table, column) typed timestamp without time zone."""
    return [f"{table}.{column} is timestamp without time zone" for table, column in rows]


@dataclass(frozen=True)
class Role:
    name: str
    superuser: bool
    create_role: bool
    create_db: bool
    connection_limit: int


def role_violations(roles: Mapping[str, Role]) -> list[str]:
    """ADR-0004-C28, ADR-0003-C19: three non-privileged roles, each limited to more than zero."""
    problems = []
    for name in ROLES:
        role = roles.get(name)
        if role is None:
            problems.append(f"{name}: missing")
            continue
        if role.superuser or role.create_role or role.create_db:
            problems.append(f"{name}: superuser, CREATEROLE or CREATEDB")
        if role.connection_limit <= 0:
            problems.append(f"{name}: connection limit {role.connection_limit}")
    return problems


def public_connect_violations(public_can_connect: Mapping[str, bool]) -> list[str]:
    """ADR-0004-C28: has_database_privilege('public', db, 'CONNECT') is false for both."""
    problems = [f"{db}: PUBLIC may connect" for db, can in public_can_connect.items() if can]
    problems += [f"{db}: not checked" for db in DATABASES if db not in public_can_connect]
    return problems


@dataclass(frozen=True)
class Budget:
    app_limit: int
    keycloak_limit: int
    backup_limit: int
    keycloak_pool_max: int
    web_workers: int
    web_pool_size: int
    web_max_overflow: int
    worker_pool_size: int
    worker_max_overflow: int
    max_connections: int
    superuser_reserved: int


def c19_violations(b: Budget) -> list[str]:
    """ADR-0003-C19 with its 2026-10-24 addendum and the limit half of ADR-0004-C19."""
    problems = []
    for name, limit in (
        ("application", b.app_limit),
        ("keycloak", b.keycloak_limit),
        ("backup", b.backup_limit),
    ):
        if limit <= 0:
            problems.append(f"{name} role limit {limit} is not greater than zero")
    if b.keycloak_pool_max > b.keycloak_limit:
        problems.append(f"db-pool-max-size {b.keycloak_pool_max} > limit {b.keycloak_limit}")
    app_use = (
        b.web_workers * (b.web_pool_size + b.web_max_overflow)
        + b.worker_pool_size
        + b.worker_max_overflow
        + MIGRATION_CONNECTIONS
    )
    if app_use > b.app_limit:
        problems.append(f"application connections at most {app_use} > limit {b.app_limit}")
    total = b.app_limit + b.keycloak_limit + b.backup_limit
    bound = b.max_connections - b.superuser_reserved
    if not total < bound:
        problems.append(f"role limits sum {total} is not below {bound}")
    return problems
