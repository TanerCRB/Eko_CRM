"""K-07 (ADR-0004 *Encryption of backups*, ADR-0005 *Places off the paths*): no part of a set,
plaintext or encrypted, is ever a file in backup's container or in a volume.

Mid-run, backup is held at H1 (the application dump has ended) and the run container's whole
filesystem, its volumes and the composition's volumes are scanned for the markers. The database
volume is left out of the marker scan only: it is the database, so it holds the rows themselves
(A-06). After a run, every file of the run container and of every volume, the database volume
included, is checked for the set's objects by digest and by each object's own age header.
"""

import hashlib
import subprocess
import time
from collections.abc import Iterator

import pytest

from tests.runtime.backup_lab import (
    KEY,
    OBJECTS,
    UNLOCK_BIGINT,
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
from tests.runtime.test_adr0004_backup_failure_line import backup_lines

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
        # Fix round 1 (R-01): the whole output, not only the lines matching the pattern.
        [line] = backup_lines(result.output)
        assert failure_lines(line) == [line], line
        fields = failure_fields(line)
        assert fields["reason"] == "interrupted", line
        backup_lab.wait_until("the lock is released", lambda: backup_lab.backup_sessions() == [])
        partial = backup_lab.double.read(f"{fields['set']}.application.dump.age")
        needles = [fields["set"].encode(), partial[HEADER_NEEDLE]]
        files = list(everything(backup_lab, name_of_container, True))
        assert files_holding(iter(files), needles) == []
    finally:
        docker("rm", "-f", name_of_container, check=False)


# QA (EKO-1-14): during the application dump, not only at H1. A dump staged in a file and removed
# once it is uploaded is gone by H1, and the Keycloak dump held at H1 has written nothing yet, so
# the H1 scan alone cannot see it. Here the application dump is made slow (padded rows) and the
# run container is searched repeatedly while it runs.

PAD_ROWS = 150_000
# A tmpfs of the run container: the place a staged dump is least visible from outside.
PLANTED_SHM = "/dev/shm/eko-test-planted"  # noqa: S108 - inside the run container only
# Every place in the run container a process can write to: the root filesystem (its writable
# layer), /dev/shm and any tmpfs; /proc and /sys are the kernel's.
SEARCH = 'grep -rlsF --exclude-dir=proc --exclude-dir=sys -e "$1" / /dev/shm; true'


def files_with(container: str, marker: str) -> list[str]:
    found = subprocess.run(
        ["docker", "exec", "-u", "0", container, "sh", "-c", SEARCH, "search", marker],
        capture_output=True, timeout=120,
    )  # fmt: skip
    return sorted(set(found.stdout.decode(errors="replace").split()))


def scans_during_the_application_dump(backup_lab: BackupLab, marker: str) -> tuple[int, list[str]]:
    """Searches the run container while its application dump runs: (scans made, files found)."""
    backup_lab.pad(PAD_ROWS)
    with backup_lab.advisory_lock_held() as holder:
        run = backup_lab.start_run()
        backup_lab.wait_until(
            "backup waits for the advisory lock",
            lambda: ("eko", "eko-backup-control", "Lock") in backup_lab.backup_sessions(),
        )
        holder.query(UNLOCK_BIGINT, k=str(KEY))
    scans, found = 0, []
    deadline = time.monotonic() + 600
    while run.running() and time.monotonic() < deadline:
        names = {s[1] for s in backup_lab.backup_sessions()}
        if "eko-backup-dump-keycloak" in names or "eko-backup-dump-roles" in names:
            break
        found += files_with(run.container_name, marker)
        scans += 1
    result = run.wait()
    assert result.code == 0, result.stderr
    return scans, found


def test_k07_during_the_application_dump_no_marker_in_the_container(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    marker = unique_marker("rest-dump")
    backup_lab.plant_row(marker)
    scans, found = scans_during_the_application_dump(backup_lab, marker)
    assert scans >= 2, f"only {scans} scans while the application dump ran"
    assert found == []


def test_k07_contrast_the_search_finds_a_marker_written_into_the_container(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    marker = unique_marker("rest-planted")
    run = backup_lab.start_run(name="bkp-rest-search", remove=False)
    try:
        with backup_lab.keycloak_table_held():
            backup_lab.wait_until("backup waits at H1", backup_lab.waiting_at_h1, 120)
            subprocess.run(
                ["docker", "exec", "-i", "bkp-rest-search", "sh", "-c", f"cat > {PLANTED_SHM}"],
                input=marker.encode("utf-8"), check=True, capture_output=True,
            )  # fmt: skip
            assert files_with("bkp-rest-search", marker) == [PLANTED_SHM]
        run.wait()
    finally:
        docker("rm", "-f", "bkp-rest-search", check=False)
