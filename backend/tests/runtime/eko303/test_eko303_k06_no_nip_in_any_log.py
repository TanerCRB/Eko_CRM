"""EKO-3-03 K-06 (ADR-0005 *What may appear in logs*, ADR-0005-C3's duplicate-save case; the
gate-1 addendum draft, section 4): no backend log record, no `migrate` output and no PostgreSQL
log line carries the NIP of a refused save, and over that window PostgreSQL writes no error,
warning, statement, detail, hint, query or context line.

PostgreSQL runs with the released `postgres` command of `compose.yaml`; the backend is the
shipped `create_app()` in-process, its records captured at DEBUG. One marker NIP goes through the
rep's duplicate save, the manager's, the K-04 overlapped loser and the K-05 refused `migrate`.

Contrast: the same duplicate save against a `postgres` started with `log_min_messages=error` and
`log_error_verbosity=default` (the two changed elements) writes a `DETAIL:` line holding the
marker, so the scenario does reach the unique constraint and the quiet window is not empty proof.
"""

import logging
import re
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI

from tests.runtime.eko201.conftest import AppFactory, Browser
from tests.runtime.eko301.conftest import REP_A, REP_AND_MANAGER, REP_B, Crm, create, created_id
from tests.runtime.eko303.conftest import (
    CommitGate,
    at_previous,
    body,
    full_body,
    overlapped,
    plant,
    refused_count,
    run_migrate,
)
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import (
    backend_records,
    logged_text,
)
from tests.support import eko302_nip as nips
from tests.support import log_lines as ll
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres, postgres
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

FORBIDDEN_LINE = re.compile(r"\b(ERROR|WARNING|STATEMENT|DETAIL|HINT|QUERY|CONTEXT):")
MARKER = nips.valid_nip(37101)
FORMS = (MARKER, nips.hyphenated(MARKER), nips.spaced(MARKER))


def release_command(**changed: str) -> list[str]:
    """The released `postgres` command's arguments after `postgres`, with settings replaced."""
    source = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    command = [str(word) for word in source["services"]["postgres"]["command"]]
    assert command[0] == "postgres", command
    arguments = command[1:]
    for name, value in changed.items():
        [index] = [i for i, word in enumerate(arguments) if word.startswith(f"{name}=")]
        arguments[index] = f"{name}={value}"
    return arguments


@pytest.fixture(scope="module")
def pg() -> Iterator[Postgres]:
    """This module's server: the released command, not the carriers' default one."""
    with postgres(release_command()) as instance:
        yield instance


@pytest.fixture(scope="module")
def contrast_pg() -> Iterator[Postgres]:
    arguments = release_command(log_min_messages="error", log_error_verbosity="default")
    with postgres(arguments) as instance:
        yield instance


class LogWindow:
    def __init__(self, pg: Postgres) -> None:
        self.container = pg.container
        self.start = len(self._lines())

    def _lines(self) -> list[str]:
        logs = subprocess.run(
            ["docker", "logs", self.container], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=True,
        )  # fmt: skip
        return (logs.stdout + logs.stderr).splitlines()

    def text(self) -> str:
        return "\n".join(self._lines()[self.start :])


def every_logger_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for name in list(logging.root.manager.loggerDict):
        if name.split(".")[0] in ("app", "migrations", "uvicorn", "fastapi", "starlette"):
            caplog.set_level(logging.DEBUG, logger=name)
    caplog.clear()


def test_k06_no_log_line_carries_the_nip_of_a_refused_save(
    crm: Crm, gate: CommitGate, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    window = LogWindow(crm.pg)
    every_logger_at_debug(caplog)
    rep_a = crm.login(REP_A, ["rep"])
    rep_b = crm.login(REP_B, ["rep"])
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    created_id(rep_a, full_body("Gospodarstwo K06", MARKER, "K06"))

    answers = [
        create(rep_b, full_body("Gospodarstwo K06 B", nips.hyphenated(MARKER), "K06B")),
        create(manager, body("Gospodarstwo K06 M", MARKER)),
    ]
    second = nips.valid_nip(37202)
    raced = overlapped(
        crm, gate, (rep_a, body("Gospodarstwo K06 wyscig A", second)),
        (rep_b, body("Gospodarstwo K06 wyscig B", second)),
    )  # fmt: skip
    assert raced.loser_waited
    answers.append(raced.loser)
    assert [a.status_code for a in answers] == [409, 409, 409]
    for answer in answers:
        assert [form for form in (*FORMS, second) if form in answer.text] == []

    at_previous(crm.pg, "eko_k06", tmp_path)
    plant(crm.pg, "eko_k06", ("PL", MARKER, None), ("PL", MARKER, None))
    code, migrate_output = run_migrate(crm.pg, "eko_k06")
    assert code != 0 and refused_count(migrate_output) == 1, migrate_output[-2000:]

    postgres_log = window.text()
    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    assert ll.leaks(logged_text(caplog.records), *FORMS, second) == []
    assert ll.leaks(migrate_output, *FORMS) == []
    assert [line for line in postgres_log.splitlines() if FORBIDDEN_LINE.search(line)] == []
    assert [form for form in (*FORMS, second) if form in postgres_log] == []
    assert "connection authorized" in postgres_log, "the window holds no line at all"


def test_k06_contrast_a_postgres_logging_errors_writes_the_marker_in_a_detail_line(
    make_app: AppFactory,
    browser_for: Callable[[FastAPI], Browser],
    stub: oidc_stub.Stub,
    contrast_pg: Postgres,
) -> None:
    app = make_app(APP_DB_PORT=str(contrast_pg.port))
    contrast = Crm(app, contrast_pg, stub, browser_for)
    window = LogWindow(contrast_pg)
    rep_a = contrast.login(REP_A, ["rep"])
    rep_b = contrast.login(REP_B, ["rep"])
    created_id(rep_a, body("Gospodarstwo K06", MARKER))
    assert create(rep_b, body("Gospodarstwo K06 B", MARKER)).status_code == 409
    details = [line for line in window.text().splitlines() if "DETAIL:" in line]
    assert any(MARKER in line for line in details), details
