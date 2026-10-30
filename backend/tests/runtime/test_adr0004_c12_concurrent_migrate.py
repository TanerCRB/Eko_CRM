"""K-01 / ADR-0004-C12: two migrate runs at once are serialised by the advisory lock.

The variant adds `t_slow_once` on top of the shipped head: it sleeps 8 s, so the overlap is forced,
and it takes one value of the sequence `eko_test_trace` per execution, which no rollback returns.
Which run wins is not asserted.
"""

import time
from dataclasses import dataclass

import pytest

from tests.runtime.lab import VARIANTS, Lab, MigrateRun
from tests.support import db_checks as dc
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
LOCK_CALL = "take_migration_lock(connection, settings.migration_advisory_lock_key)"
OVERLAP_SECONDS = 20


@dataclass
class Outcome:
    observed_waiting: bool
    codes: list[int]
    versions: list[str] | None
    heads: str
    trace: int
    logs: str


def overlap_observed(lab: Lab, runs: tuple[MigrateRun, MigrateRun]) -> bool:
    classid, objid, objsubid = mc.pg_locks_identity(KEY)
    holding = waiting = None
    for run in runs:
        for lock in lab.advisory_locks(run):
            if lock[:3] == (classid, objid, objsubid):
                if lock[3]:
                    holding = run
                else:
                    waiting = run
    if holding is None or waiting is None or holding is waiting:
        return False
    return any("pg_sleep" in query for _, _, query in lab.activity(holding))


def concurrent(lab: Lab, image: str) -> Outcome:
    lab.reset()
    lab.sql("CREATE SEQUENCE eko_test_trace")
    lab.sql("GRANT USAGE ON SEQUENCE eko_test_trace TO eko_app")
    runs = (lab.start_migrate(image), lab.start_migrate(image))
    try:
        observed = False
        deadline = time.monotonic() + OVERLAP_SECONDS
        while not observed and time.monotonic() < deadline and all(r.running() for r in runs):
            observed = overlap_observed(lab, runs)
            time.sleep(0.05)
        codes = [run.wait(120) for run in runs]
        logs = "\n".join(run.logs() for run in runs)
    finally:
        for run in runs:
            run.remove()
    [[trace]] = lab.sql("SELECT CASE WHEN is_called THEN last_value ELSE 0 END FROM eko_test_trace")
    heads = lab.image_command(image, "alembic", "heads").stdout
    return Outcome(observed, codes, lab.versions(), heads, int(trace), logs[-4000:])


def test_adr0004_c12_concurrent_migrate(lab: Lab) -> None:
    outcome = concurrent(lab, lab.variant("slow_once"))
    assert outcome.observed_waiting, outcome.logs
    assert outcome.codes == [0, 0], outcome.logs
    assert dc.c2_heads(outcome.heads, outcome.versions or []) == []
    assert outcome.versions == ["t_slow_once"]
    assert outcome.trace == 1


def test_adr0004_c12_contrast_without_the_lock_the_concurrent_scenario_fails(lab: Lab) -> None:
    # Planted contrast (addendum: a fixture changing env.py proves nothing on its own).
    image = lab.planted_env_py("no_lock", LOCK_CALL, "pass", VARIANTS["slow_once"])
    outcome = concurrent(lab, image)
    holds = outcome.observed_waiting and outcome.codes == [0, 0] and outcome.trace == 1
    assert not holds, outcome
