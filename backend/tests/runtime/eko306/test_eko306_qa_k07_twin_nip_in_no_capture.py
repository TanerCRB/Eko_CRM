"""EKO-3-06 K-07, QA contrast: the NIP of the K-04 twin, the one dataset value that ever reaches a
driver's unique-violation message, appears in no capture.

The developer K-07 test samples every 37th dataset record for its markers, and the twin (the first
dataset record with a NIP) is not among them, so a seed that prints the driver's message on a NIP
refusal passed that test (QA mutation run, 2026-11-25). Here the markers are exactly the twin's
NIP as stored, hyphenated, and as the dataset spells it, and the run that refuses the twin is
captured the same ways: stdout and stderr of the in-process runs and of `python -m app.seed`,
every in-process logger at DEBUG (`sqlalchemy` and `psycopg` included), and the log of a
PostgreSQL started with the released `postgres` command.

Contrast: the refusal itself is reported (CUS-6, by dataset key), and a line the harness plants
with the twin's NIP is found, so the captures are not blind.
"""

import logging
from collections.abc import Iterator

import pytest

from app.domain.customers import customer_draft
from app.seed_dataset import Record, records
from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko303.test_eko303_k06_no_nip_in_any_log import (
    LogWindow,
    every_logger_at_debug,
    release_command,
)
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import logged_text
from tests.runtime.eko306.conftest import SEED_A, Seeder, seed_process
from tests.support import eko302_nip as nips
from tests.support import log_lines as ll
from tests.support.pg_instance import Postgres, postgres

pytestmark = pytest.mark.runtime


@pytest.fixture(scope="module")
def pg() -> Iterator[Postgres]:
    """This module's server: the released `postgres` command, as in the developer K-07 test."""
    with postgres(release_command()) as instance:
        yield instance


def the_twin() -> tuple[Record, str]:
    for record in records():
        nip = customer_draft(record.customer).tax_id.nip
        if nip is not None:
            return record, nip
    raise AssertionError("the dataset holds no NIP")


def test_qa_k07_the_twin_nip_a_driver_refusal_carries_reaches_no_capture(
    crm: Crm, seed: Seeder, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    window = LogWindow(crm.pg)
    every_logger_at_debug(caplog)
    for name in ("sqlalchemy", "psycopg"):
        caplog.set_level(logging.DEBUG, logger=name)
    twin, nip = the_twin()
    created = create(crm.login(SEED_A, ["rep"]), {"name": "Gospodarstwo QA K07", "tax_id": nip})
    assert created.status_code == 201, created.text[:300]
    markers = {nip, nips.hyphenated(nip), twin.customer.tax_id or nip}

    run = seed()
    again = seed()
    done = seed_process(crm.pg)
    # The driver refused the twin each time, so its message existed to be printed.
    assert run.refused() == again.refused() == {twin.key: ("CUS-6", "tax_id")}
    assert done.returncode != 0 and twin.key in done.stderr

    captured = capsys.readouterr()
    output = "\n".join([captured.out, captured.err, done.stdout, done.stderr])
    assert ll.leaks(output, *markers) == []
    assert ll.leaks(logged_text(caplog.records), *markers) == []
    postgres_log = window.text()
    assert "connection authorized" in postgres_log, "the window holds no line at all"
    assert [m for m in markers if m in postgres_log] == []

    logging.getLogger("app.seed").warning("planted %s", nip)
    assert ll.leaks(logged_text(caplog.records), nip) == [nip]
