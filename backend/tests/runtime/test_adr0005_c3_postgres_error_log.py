"""EKO-1-13 K-01: PostgreSQL writes no line for a failed statement, on both databases and for
every role, while its connection and authentication events stay (ADR-0005-C3; addendum of
2026-11-02, Q-1 A, Q-2 B).

The statements go straight to PostgreSQL over database sessions opened from the `backend`
container (so they authenticate by password, as the services do), never through `backend`'s
code. A backend that swallowed the error would prove nothing about PostgreSQL's log.

Contrast: the same statements on a `postgres` started with the released command except
`log_min_messages`, back at the image's default (one element changed), leave an ERROR line with
the marker, and the window check fails on it.
"""

import json
import re
import secrets
import uuid
from typing import Any

import pytest
import yaml

from tests.runtime.conftest import Started
from tests.runtime.eko113 import json_result, python_in_service, window
from tests.runtime.lab import docker
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

TOKEN = secrets.token_hex(5)
MARKER = f"marker-c3-{TOKEN}"
NON_ASCII = f"Zażółć-c3-{TOKEN}"
LONG = f"long-c3-{TOKEN}-" + "y" * 1500
ROLE_MARKER = f"marker-role-{TOKEN}"
DB_MARKER = f"marker-db-{TOKEN}"
APP_MARKER = f"marker-app-{TOKEN}"
# Fixed: each composition is fresh, and the table is dropped by the statements below.
TABLE = "eko113_c3_probe"
STATEMENT_MARKERS = (MARKER, NON_ASCII, LONG[:30], TABLE)
FORBIDDEN_LINE = re.compile(r"\b(ERROR|WARNING|STATEMENT|DETAIL|HINT|QUERY|CONTEXT):")

PROBE = """
import json, psycopg
out = []
for case in json.loads(CASES):
    try:
        with psycopg.connect(host="postgres", dbname=case["db"], user=case["user"],
                             password=case["password"], application_name=case["app"],
                             connect_timeout=5, autocommit=True) as conn:
            for sql, params in case["statements"]:
                try:
                    conn.execute(sql, params)
                    out.append([case["label"], sql[:20], "ok"])
                except psycopg.Error as exc:
                    out.append([case["label"], sql[:20], exc.sqlstate])
    except psycopg.Error as exc:
        # psycopg sets no SQLSTATE on a refused start-up; the server log line carries it.
        out.append([case["label"], "connect", exc.sqlstate or type(exc).__name__])
print(json.dumps({"results": out}))  # leftovers-allow: container probe; stdout is its answer
"""


def failing_statements(own_table: bool) -> list[tuple[str, list[str]]]:
    statements: list[tuple[str, list[str]]] = []
    if own_table:
        statements += [
            ("CREATE TABLE eko113_c3_probe (v text UNIQUE)", []),
            ("INSERT INTO eko113_c3_probe (v) VALUES (%s)", [MARKER]),
            ("INSERT INTO eko113_c3_probe (v) VALUES (%s)", [MARKER]),
        ]
    statements += [
        ("SELECT %s::date", [MARKER]),
        ("SELECT %s::integer", [NON_ASCII]),
        ("SELECT %s::date", [LONG]),
        # An unknown identifier, which an error CONTEXT or HINT would quote.
        (f'SELECT * FROM "{MARKER}"', []),  # noqa: S608  # a synthetic marker, test-only
        (f"SELECT {MARKER.replace('-', '_')}()", []),
        ("SELECT pg_sleep(1.2)", []),
    ]
    if own_table:
        statements.append(("DROP TABLE eko113_c3_probe", []))
    return statements


def cases(env: dict[str, str]) -> list[dict[str, Any]]:
    roles = {
        "eko_app": env["APP_DB_PASSWORD"],
        "eko_keycloak": env["KEYCLOAK_DB_PASSWORD"],
        "eko_backup": env["BACKUP_DB_PASSWORD"],
        "postgres": env["POSTGRES_PASSWORD"],
    }
    found = []
    for user, db, own_table in [
        ("eko_app", "eko", True),
        ("eko_keycloak", "keycloak", True),
        ("eko_backup", "eko", False),
        ("eko_backup", "keycloak", False),
        ("postgres", "eko", True),
        ("postgres", "keycloak", True),
    ]:
        statements = failing_statements(own_table)
        found.append({"label": f"{user}@{db}", "user": user, "db": db, "app": "",
                      "password": roles[user], "statements": statements})  # fmt: skip
    found += [
        {"label": "marker-role", "user": ROLE_MARKER, "db": "eko", "app": "",
         "password": f"wrong-{TOKEN}", "statements": []},
        {"label": "marker-db", "user": "eko_app", "db": DB_MARKER, "app": "",
         "password": roles["eko_app"], "statements": []},
        {"label": "marker-app", "user": "eko_app", "db": "eko", "app": APP_MARKER,
         "password": roles["eko_app"], "statements": [("SELECT 1", [])]},
    ]  # fmt: skip
    return found


def run_probe(started: Started) -> list[list[str]]:
    script = PROBE.replace("CASES", repr(json.dumps(cases(started.composition.env))))
    result = python_in_service(started.composition, "backend", script, timeout=180)
    results: list[list[str]] = json_result(result)["results"]
    return results


def window_problems(text: str, sessions: list[tuple[str, str]]) -> list[str]:
    """K-01's window rules; `sessions` are the (role, database) pairs whose events must show."""
    lines = text.splitlines()
    problems = [f"forbidden line: {line[:300]!r}" for line in lines if FORBIDDEN_LINE.search(line)]
    for marker in STATEMENT_MARKERS:
        problems += [f"statement marker in {line[:300]!r}" for line in lines if marker in line]
    role_lines = [line for line in lines if ROLE_MARKER in line]
    if len(role_lines) != 1 or not re.search(r" 28P01 .*FATAL:", role_lines[0]):
        problems.append(f"marker role lines {role_lines}")
    db_fatal = [line for line in lines if DB_MARKER in line and "FATAL:" in line]
    if len(db_fatal) != 1 or " 3D000 " not in db_fatal[0]:
        problems.append(f"marker database FATAL lines {db_fatal}")
    for line in lines:
        if DB_MARKER in line and "FATAL:" not in line and "LOG:  connection " not in line:
            problems.append(f"marker database outside a connection event: {line!r}")
        if APP_MARKER in line and "connection authorized:" not in line:
            problems.append(f"application_name outside the authorization event: {line!r}")
    if not any(APP_MARKER in line for line in lines):
        problems.append("no authorization event names the session's application_name")
    for user, db in sessions:
        for event in (f"connection authorized: user={user} database={db}",
                      "disconnection: session time:"):  # fmt: skip
            if not any(event in line and f"{user}@{db}" in line for line in lines):
                problems.append(f"no {event!r} line for {user}@{db}")
        if not any(
            "connection authenticated:" in line and f"{user}@{db}" in line for line in lines
        ):
            problems.append(f"no authentication event for {user}@{db}")
    if not any("connection received:" in line for line in lines):
        problems.append("no connection receipt event")
    return problems


SESSIONS = [("eko_app", "eko"), ("eko_keycloak", "keycloak"), ("eko_backup", "eko"),
            ("eko_backup", "keycloak"), ("postgres", "eko"), ("postgres", "keycloak")]  # fmt: skip


def test_adr0005_c3_postgres_error_log(running: Started) -> None:
    mark = window(running.composition, "postgres")
    results = run_probe(running)
    text = mark.text(settle=2)
    failed = {state for _, _, state in results if state != "ok"}
    # The statements did fail, each for its own reason: the window is not quiet by accident.
    assert {"23505", "22007", "22P02", "42P01", "42883"} <= failed, results
    connects = {label: state for label, step, state in results if step == "connect"}
    assert set(connects) == {"marker-role", "marker-db"}, results
    assert all(state != "ok" for state in connects.values())
    assert window_problems(text, SESSIONS) == []


def test_adr0005_c3_postgres_log_destination_and_no_per_scope_setting(running: Started) -> None:
    sql = running.composition.sql
    assert sql("SHOW logging_collector") == [["off"]]
    assert sql("SHOW log_destination") == [["stderr"]]
    assert sql("SHOW log_min_messages") == [["log"]]
    per_scope = sql(
        "SELECT count(*) FROM pg_db_role_setting, unnest(setconfig) AS s "
        "WHERE s ~* '^(log_|logging_collector)'"
    )
    assert per_scope == [["0"]]


def test_adr0005_c3_postgres_error_log_contrast_default_log_min_messages() -> None:
    """The released command minus `log_min_messages`: the image's default writes the ERROR."""
    source = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    postgres = source["services"]["postgres"]
    command = [str(word) for word in postgres["command"]]
    index = command.index("log_min_messages=log")
    command = command[: index - 1] + command[index + 1 :]
    name = f"eko113-c3-contrast-{uuid.uuid4().hex[:8]}"
    docker(
        "run", "-d", "--name", name, "-e", "=".join(("POSTGRES_PASSWORD", f"contrast-{TOKEN}")),
        postgres["image"], *command,
    )  # fmt: skip
    try:
        for _ in range(60):
            ready = docker("exec", name, "pg_isready", "-h", "127.0.0.1", check=False)
            if ready.returncode == 0:
                break
            docker("exec", name, "sleep", "1", check=False)
        start = len(docker("logs", name, check=False).stderr.splitlines())
        docker(
            "exec", name, "psql", "-U", "postgres", "-h", "127.0.0.1", "-X",
            "-c", f"SELECT '{MARKER}'::date", check=False,
        )  # fmt: skip
        docker("exec", name, "sleep", "1", check=False)
        text = "\n".join(docker("logs", name, check=False).stderr.splitlines()[start:])
    finally:
        docker("rm", "-f", name, check=False)
    problems = window_problems(text, [])
    assert any(p.startswith("forbidden line") and "ERROR:" in p for p in problems), problems
    assert any(p.startswith("statement marker") for p in problems), problems
