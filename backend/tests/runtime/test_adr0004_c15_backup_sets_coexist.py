"""K-04 (ADR-0004-C15, several sets): every run adds one new, distinct, complete set. A
scheduled-path run and an on-demand run leave two sets, two runs started together leave two, and
the first run into an empty destination succeeds.
"""

import pytest

from tests.runtime.backup_lab import (
    BackupLab,
    backup_environment,
    complete_sets,
    open_set,
    set_names,
    unique_marker,
)

pytestmark = pytest.mark.runtime


def assert_set_checks(backup_lab: BackupLab, name: str, marker: str) -> None:
    """K-03's checks that need no held run: complete, decrypts, both dumps, roles, manifest."""
    assert name in complete_sets(backup_lab.double)
    contents = open_set(backup_lab.double, name, backup_lab.identity)
    assert marker.encode("utf-8") in contents.application
    assert contents.keycloak.startswith(b"PGDMP")
    assert contents.application.startswith(b"PGDMP")
    assert b"CREATE ROLE eko_backup;" in contents.roles
    assert b"PASSWORD" not in contents.roles.upper()
    assert contents.manifest["set"] == name
    assert contents.manifest["alembic_revision"] == "t_backup_probe"


def test_k04_a_scheduled_and_an_on_demand_run_leave_two_distinct_sets(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    marker = unique_marker("k04")
    backup_lab.plant_row(marker)
    before = set_names(backup_lab.double)
    scheduled = backup_lab.run()
    assert scheduled.code == 0, scheduled.stderr
    after_scheduled = set_names(backup_lab.double)
    on_demand = backup_lab.on_demand().wait()
    assert on_demand.code == 0, on_demand.stderr
    first = after_scheduled - before
    second = set_names(backup_lab.double) - after_scheduled
    assert len(first) == 1 and len(second) == 1 and first != second
    assert first <= set_names(backup_lab.double), "the second run replaced the first"
    for name in first | second:
        assert_set_checks(backup_lab, name, marker)


def test_k04_edge_two_on_demand_runs_started_together_leave_two_sets(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    runs = [backup_lab.on_demand(), backup_lab.on_demand()]
    results = [run.wait() for run in runs]
    assert [r.code for r in results] == [0, 0], [r.stderr for r in results]
    new = set_names(backup_lab.double) - before
    assert len(new) == 2
    assert new <= complete_sets(backup_lab.double)


def test_k04_edge_the_first_run_into_an_empty_destination_succeeds(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    double = backup_lab.double
    directory = double.new_directory()
    assert double.objects(directory) == {}
    destination = backup_environment(double, backup_lab.recipient)["BACKUP_DESTINATION"]
    destination = destination.rsplit("/", 1)[0] + directory
    result = backup_lab.run(env={"BACKUP_DESTINATION": destination})
    assert result.code == 0, result.stderr
    assert len(complete_sets(double, directory)) == 1
