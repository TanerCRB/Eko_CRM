"""K-07 (ADR-0004 *Encryption of backups*, ADR-0005 *Places off the paths*): no part of a set,
plaintext or encrypted, is ever a file in backup's container or in a volume.

Mid-run, backup is held at H1 (the application dump has ended) and the run container's whole
filesystem, its volumes and the composition's volumes are scanned for the markers. The database
volume is left out of the marker scan only: it is the database, so it holds the rows themselves
(A-06). After a run, every file of the run container and of every volume, the database volume
included, is checked for the set's objects by digest and by each object's own age header.
"""

import hashlib
from collections.abc import Iterator

import pytest

from tests.runtime.backup_lab import (
    OBJECTS,
    BackupLab,
    container_files,
    failure_fields,
    failure_lines,
    files_holding,
    files_with_digest,
    open_set,
    project_volumes,
    set_names,
    unique_marker,
    volume_files,
)
from tests.runtime.lab import docker

pytestmark = pytest.mark.runtime

HEADER_NEEDLE = slice(22, 80)


def everything(
    backup_lab: BackupLab, container: str, with_database: bool
) -> Iterator[tuple[str, bytes]]:
    yield from container_files(container)
    for volume in project_volumes(backup_lab.composition):
        if with_database or not volume.endswith("_pgdata"):
            yield from volume_files(volume)


def set_traces(backup_lab: BackupLab, name: str) -> tuple[set[str], list[bytes]]:
    """Digests of the set's five uploaded objects, and needles that also find a part of one."""
    double = backup_lab.double
    digests, needles = set(), [name.encode()]
    for suffix in (*OBJECTS, "complete"):
        data = double.read(f"{name}.{suffix}")
        digests.add(hashlib.sha256(data).hexdigest())
        if suffix != "complete":
            needles.append(data[HEADER_NEEDLE])
    return digests, needles


def test_k07_mid_run_no_marker_in_the_container_or_a_volume(backup_lab: BackupLab) -> None:
    backup_lab.at_probe_head()
    markers = [unique_marker("rest-row"), unique_marker("rest-user")]
    backup_lab.plant_row(markers[0])
    backup_lab.plant_keycloak_user(markers[1])
    before = set_names(backup_lab.double)
    with backup_lab.keycloak_table_held():
        run = backup_lab.start_run()
        backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
        assert not [s for s in backup_lab.dump_sessions() if s[0] == "eko"]
        needles = [m.encode("utf-8") for m in markers]
        found = files_holding(everything(backup_lab, run.container_name, False), needles)
        assert found == []
    result = run.wait()
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    decrypted = open_set(backup_lab.double, name, backup_lab.identity)
    assert files_holding(iter([("dump", decrypted.application)]), needles[:1]) == ["dump"]


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_k07_after_a_run_no_file_holds_the_sets_bytes(backup_lab: BackupLab, outcome: str) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    name_of_container = f"bkp-rest-{outcome}"
    if outcome == "failure":
        backup_lab.double.set_mode("lose-complete")
    try:
        result = backup_lab.run(name=name_of_container, remove=False)
    finally:
        backup_lab.double.set_mode("on")
    try:
        if outcome == "failure":
            assert result.code != 0
            [line] = failure_lines(result.stderr)
            assert failure_fields(line)["reason"] == "destination"
            # The lost record is the double's doing; its digest is the bytes backup sent.
        else:
            assert result.code == 0, result.stderr
        [name] = set_names(backup_lab.double) - before
        if outcome == "failure":
            digests, needles = set(), [name.encode()]
            for suffix in OBJECTS:
                data = backup_lab.double.read(f"{name}.{suffix}")
                digests.add(hashlib.sha256(data).hexdigest())
                needles.append(data[HEADER_NEEDLE])
        else:
            digests, needles = set_traces(backup_lab, name)
        files = list(everything(backup_lab, name_of_container, True))
        assert files, "the scan saw no file"
        assert files_with_digest(iter(files), digests) == []
        assert files_holding(iter(files), needles) == []
    finally:
        docker("rm", "-f", name_of_container, check=False)


def test_k07_contrast_a_file_holding_the_sets_bytes_is_found(backup_lab: BackupLab) -> None:
    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    result = backup_lab.run(name="bkp-rest-planted", remove=False)
    try:
        assert result.code == 0, result.stderr
        [name] = set_names(backup_lab.double) - before
        digests, needles = set_traces(backup_lab, name)
        data = backup_lab.double.read(f"{name}.application.dump.age")
        planted = [("planted", data), ("partial", data[:4096])]
        files = list(everything(backup_lab, "bkp-rest-planted", True)) + planted
        assert files_with_digest(iter(files), digests) == ["planted"]
        assert files_holding(iter(files), needles) == ["partial", "planted"]
    finally:
        docker("rm", "-f", "bkp-rest-planted", check=False)


def test_k07_g8_an_interrupted_run_writes_one_line_and_leaves_nothing(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    name_of_container = "bkp-rest-interrupted"
    with backup_lab.keycloak_table_held():
        run = backup_lab.start_run(name=name_of_container, remove=False)
        backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
        docker("stop", name_of_container, timeout=60)
        result = run.wait()
    try:
        assert result.code != 0
        [line] = failure_lines(result.stderr)
        fields = failure_fields(line)
        assert fields["reason"] == "interrupted", line
        backup_lab.wait_until("the lock is released", lambda: backup_lab.backup_sessions() == [])
        partial = backup_lab.double.read(f"{fields['set']}.application.dump.age")
        needles = [fields["set"].encode(), partial[HEADER_NEEDLE]]
        files = list(everything(backup_lab, name_of_container, True))
        assert files_holding(iter(files), needles) == []
    finally:
        docker("rm", "-f", name_of_container, check=False)
