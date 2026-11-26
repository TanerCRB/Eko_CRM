"""EKO-3-06 K-07 (ADR-0005 *What may appear in logs*, the seed as "any worker"; ADR-0005-C23): no
customer value reaches the seed's output or any log, the refused records' included.

Captured: standard output and error of the in-process runs and of `python -m app.seed` runs;
every in-process logger at DEBUG (root, `app`, `sqlalchemy`, `migrations`); and the log of a
PostgreSQL started with the released `postgres` command of `compose.yaml`. The runs: a full load,
a re-run, a run with every K-02 refused case injected, the K-04 twin (a dataset NIP a rep holds)
and the K-05 refusal of an undeclared target.

Markers: the names, phones, e-mails, streets and NIPs (plain and hyphenated) of the injected
records and of sampled dataset records. None appears in any capture; a refused record is named
by its dataset key and rule only.

Contrast: a line the same harness plants with one marker is found, and the refused records' rule
and field names do appear in the report, so the captures are not blind.
"""

import logging
from collections.abc import Iterator

import pytest

from app.domain.customers import CustomerInput, CustomerRefused, customer_draft
from app.seed_dataset import Record, records
from tests.runtime.eko301.conftest import Crm, create
from tests.runtime.eko303.test_eko303_k06_no_nip_in_any_log import (
    FORBIDDEN_LINE,
    LogWindow,
    every_logger_at_debug,
    release_command,
)
from tests.runtime.eko304.test_eko304_k06_literal_input_no_echo import logged_text
from tests.runtime.eko306.conftest import SEED_A, Seeder, fresh_database, seed_process
from tests.support import eko302_nip as nips
from tests.support import log_lines as ll
from tests.support.eko306_cases import CASES, normalised_record
from tests.support.pg_instance import Postgres, postgres

pytestmark = pytest.mark.runtime

SAMPLE_EVERY = 37


@pytest.fixture(scope="module")
def pg() -> Iterator[Postgres]:
    """This module's server: the released `postgres` command, not the carriers' default one."""
    with postgres(release_command()) as instance:
        yield instance


def markers_of(given: CustomerInput) -> set[str]:
    found = {given.name.strip(), given.street or ""}
    for contact in given.contacts:
        found |= {contact.value.strip(), contact.note or ""}
    if given.tax_id:
        found.add(given.tax_id)
    try:
        draft = customer_draft(given)
    except CustomerRefused:
        draft = None
    if draft is not None:
        found |= {draft.name} | {c.value for c in draft.contacts}
        if draft.tax_id.nip:
            found |= {draft.tax_id.nip, nips.hyphenated(draft.tax_id.nip)}
    # Notes repeat across records and are common words; they are not identifying markers.
    notes = {c.note for c in given.contacts if c.note}
    return {m for m in found - notes if m and len(m) >= 6}


def every_marker(injected: list[CustomerInput]) -> set[str]:
    sampled = [r.customer for r in records()[::SAMPLE_EVERY]]
    return set().union(*(markers_of(given) for given in [*injected, *sampled]))


def test_k07_no_customer_value_reaches_output_logs_or_postgresql(
    crm: Crm, seed: Seeder, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    window = LogWindow(crm.pg)
    every_logger_at_debug(caplog)
    for name in ("sqlalchemy", "migrations", "psycopg"):
        caplog.set_level(logging.DEBUG, logger=name)
    refused = [CASES[case].refused for case in sorted(CASES)]
    injected = [*refused, normalised_record()]
    twin = next(r for r in records() if customer_draft(r.customer).tax_id.nip)
    twin_nip = customer_draft(twin.customer).tax_id.nip
    assert twin_nip is not None
    created = create(crm.login(SEED_A, ["rep"]), {"name": "Gospodarstwo K07 B", "tax_id": twin_nip})
    assert created.status_code == 201, created.text[:300]

    runs = [
        seed(),
        seed(),
        seed(records=[Record(f"k07-{i}", 0, given) for i, given in enumerate(injected)]),
        seed(declared="false"),
    ]
    # The twin's NIP stays with the rep's customer, so every load and re-run reports it.
    assert [run.code != 0 for run in runs] == [True, True, True, True]
    assert runs[0].refused() == {twin.key: ("CUS-6", "tax_id")}
    assert len(runs[2].refused()) == len(refused)
    fresh_database(crm.pg, "eko306_k07_process")
    processes = [seed_process(crm.pg, database="eko306_k07_process")]
    processes.append(seed_process(crm.pg, database="eko306_k07_process", declared=None))
    assert [p.returncode for p in processes][0] == 0 and processes[1].returncode != 0

    captured = capsys.readouterr()
    output = "\n".join(
        [captured.out, captured.err, *(p.stdout + p.stderr for p in processes)]
        + [run.refusal or "" for run in runs]
    )
    logs = logged_text(caplog.records)
    postgres_log = window.text()
    markers = every_marker(injected)
    assert len(markers) > 50
    assert ll.leaks(output, *markers) == []
    assert ll.leaks(logs, *markers) == []
    assert [m for m in markers if m in postgres_log] == []
    assert [line for line in postgres_log.splitlines() if FORBIDDEN_LINE.search(line)] == []
    assert "connection authorized" in postgres_log, "the window holds no line at all"

    # The report names the rule and field, and only the dataset key, of each refused record.
    assert "CUS-5 (tax_id)" in logs and "CUS-8 (contacts.value)" in logs and twin.key in logs
    assert "seed finished" in processes[0].stderr

    marker = sorted(markers)[0]
    logging.getLogger("app.seed").warning("planted %s", marker)
    assert ll.leaks(logged_text(caplog.records), marker) == [marker]
