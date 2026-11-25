"""EKO-3-05 K-03, no log carries the NIP of a refused edit (ADR-0005 *What may appear in logs*;
ADR-0003-C40; K-03 M-k9): on the carrier of EKO-3-03 K-06 (capability row 74), PostgreSQL started
with the released `postgres` command and the backend in-process with every logger at DEBUG, the
NIP of a refused edit, plain, hyphenated or spaced, appears in no backend record and no
PostgreSQL line, and PostgreSQL writes no error, statement or detail line over that window.

Contrast: the same refused edit against a `postgres` started with `log_min_messages=error` and
`log_error_verbosity=default` (the two changed elements) writes a `DETAIL:` line holding the NIP,
so the scenario does reach the unique constraint.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI

from tests.runtime.eko201.conftest import AppFactory, Browser
from tests.runtime.eko301.conftest import REP_A, REP_AND_MANAGER, REP_B, Crm
from tests.runtime.eko303.test_eko303_k06_no_nip_in_any_log import (
    FORBIDDEN_LINE,
    LogWindow,
    every_logger_at_debug,
    release_command,
)
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import (
    backend_records,
    logged_text,
)
from tests.runtime.eko305.conftest import customer, edit
from tests.support import eko302_nip as nips
from tests.support import log_lines as ll
from tests.support import oidc_stub
from tests.support.pg_instance import Postgres, postgres

pytestmark = pytest.mark.runtime

MARKER = nips.valid_nip(305951)
FORMS = (MARKER, nips.hyphenated(MARKER), nips.spaced(MARKER))


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


def refused_edits(crm: Crm) -> None:
    rep_a, rep_b = crm.login(REP_A, ["rep"]), crm.login(REP_B, ["rep"])
    manager = crm.login(REP_AND_MANAGER, ["rep", "manager"])
    customer(rep_a, "Gospodarstwo X", tax_id=MARKER)
    y, z = customer(rep_a, "Gospodarstwo Y"), customer(rep_b, "Gospodarstwo Z")
    answers = [
        edit(rep_a, y, {"name": "Gospodarstwo Y", "tax_id": MARKER}),
        edit(rep_b, z, {"name": "Gospodarstwo Z", "tax_id": nips.hyphenated(MARKER)}),
        edit(manager, z, {"name": "Gospodarstwo Z", "tax_id": nips.spaced(MARKER)}),
    ]
    assert [a.status_code for a in answers] == [409, 409, 409], [a.text for a in answers]
    for answer in answers:
        assert [form for form in FORMS if form in answer.text] == []


def test_k03_no_log_line_carries_the_nip_of_a_refused_edit(
    crm: Crm, caplog: pytest.LogCaptureFixture
) -> None:
    window = LogWindow(crm.pg)
    every_logger_at_debug(caplog)
    refused_edits(crm)
    postgres_log = window.text()
    assert backend_records(caplog.records), "no backend record: the capture would be vacuous"
    assert ll.leaks(logged_text(caplog.records), *FORMS) == []
    assert [line for line in postgres_log.splitlines() if FORBIDDEN_LINE.search(line)] == []
    assert [form for form in FORMS if form in postgres_log] == []
    assert "connection authorized" in postgres_log, "the window holds no line at all"


def test_k03_contrast_a_verbose_postgres_logs_the_nip_of_the_same_refused_edit(
    make_app: AppFactory,
    browser_for: Callable[[FastAPI], Browser],
    stub: oidc_stub.Stub,
    contrast_pg: Postgres,
) -> None:
    contrast = Crm(make_app(APP_DB_PORT=str(contrast_pg.port)), contrast_pg, stub, browser_for)
    window = LogWindow(contrast_pg)
    refused_edits(contrast)
    details = [line for line in window.text().splitlines() if "DETAIL:" in line]
    assert any(MARKER in line for line in details), details
