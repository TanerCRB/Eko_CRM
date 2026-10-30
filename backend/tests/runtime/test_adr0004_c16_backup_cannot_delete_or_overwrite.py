"""K-04 (ADR-0004-C16 against the double): backup never attempts a delete, an overwrite or a
rewritten pointer, and the double refuses both delete and overwrite to backup's credential.

The claim about the service is read from the double's record of every attempted request, refused
or not; a service whose deletes the double refuses would otherwise pass on what survives.
"""

from typing import Any

import pytest

from tests.runtime.backup_lab import INCOMING, BackupLab, Double, set_names

pytestmark = pytest.mark.runtime

BACKUP = "eko-backup"
ADMIN = "root"
ATTRIBUTE_READS = {"init", "realpath", "stat", "lstat", "fstat"}
RUNS = 3
# The test's own SFTP attempts run inside the double, so they arrive from its loopback address.
TEST_CLIENT = "127.0.0.1"


def non_adds(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every request that is neither part of an add nor a read of attributes.

    An add is the create of a name that did not exist, its writes and its close; an open of an
    existing name for writing, any remove, rename, setstat, link or extension is not.
    """
    found = []
    for record in records:
        request = record["request"]
        if request in ATTRIBUTE_READS or request in {"write", "close"}:
            continue
        flags = set(record.get("flags", []))
        if request == "open" and not record["existed"] and {"WRITE", "CREAT"} <= flags:
            continue
        found.append(record)
    return found


def own_records(double: Double, since: int) -> list[dict[str, Any]]:
    return [r for r in double.records()[since:] if r["credential"] == BACKUP]


def test_k04_backups_record_over_three_runs_shows_only_adds(backup_lab: BackupLab) -> None:
    backup_lab.at_probe_head()
    double = backup_lab.double
    since = len(double.records())
    before = set_names(double)
    for _ in range(RUNS):
        result = backup_lab.run()
        assert result.code == 0, result.stderr
    assert len(set_names(double) - before) == RUNS
    records = own_records(double, since)
    assert [r for r in records if r["request"] == "open"], "the record holds no add at all"
    assert non_adds(records) == []
    # Every request the service sent in this lab; the test's own attempts come from the double.
    service = [r for r in double.records() if r["credential"] == BACKUP]
    assert non_adds([r for r in service if r["client"] != TEST_CLIENT]) == []


def sacrificial_object(backup_lab: BackupLab) -> str:
    before = set_names(backup_lab.double)
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    return f"{name}.manifest.json.age"


def test_k04_backups_credential_cannot_delete_or_overwrite_a_set(backup_lab: BackupLab) -> None:
    backup_lab.at_probe_head()
    double = backup_lab.double
    target = sacrificial_object(backup_lab)
    original = double.read(target)
    since = len(double.records())
    deleted = double.sftp(BACKUP, f"rm {INCOMING}/{target}\n")
    overwritten = double.sftp(BACKUP, f"put /etc/hostname {INCOMING}/{target}\n")
    assert deleted.returncode != 0 and overwritten.returncode != 0
    assert double.read(target) == original
    attempts = non_adds(own_records(double, since))
    assert {r["request"] for r in attempts} >= {"remove", "open"}, attempts
    assert all(r["existed"] for r in attempts if r["request"] in {"remove", "open"})


def test_k04_contrast_the_administrative_credential_deletes_and_overwrites(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    double = backup_lab.double
    target = sacrificial_object(backup_lab)
    original = double.read(target)
    overwritten = double.sftp(ADMIN, f"put /etc/hostname {INCOMING}/{target}\n")
    assert overwritten.returncode == 0, overwritten.stderr
    assert double.read(target) != original
    deleted = double.sftp(ADMIN, f"rm {INCOMING}/{target}\n")
    assert deleted.returncode == 0, deleted.stderr
    assert target not in double.objects()


def test_k04_contrast_with_refusal_off_the_record_sees_a_delete_and_an_overwrite(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    double = backup_lab.double
    targets = [sacrificial_object(backup_lab), sacrificial_object(backup_lab)]
    since = len(double.records())
    double.set_mode("off")
    try:
        # What a pruning service and a "latest"-rewriting service would send with this credential.
        assert double.sftp(BACKUP, f"rm {INCOMING}/{targets[0]}\n").returncode == 0
        double.sftp(BACKUP, f"put /etc/hostname {INCOMING}/{targets[1]}\n")
    finally:
        double.set_mode("on")
    seen = non_adds(own_records(double, since))
    assert any(r["request"] == "remove" and r["name"].endswith(targets[0]) for r in seen), seen
    assert any(r["request"] == "open" and r["name"].endswith(targets[1]) for r in seen), seen
