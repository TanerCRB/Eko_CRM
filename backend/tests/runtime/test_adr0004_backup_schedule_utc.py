"""K-05, schedule: backup's own main process is a scheduler that has loaded exactly one daily
entry at 01:00 UTC, which runs the command K-01 runs, in a container whose zone is UTC.

The check proves the entry is loaded, not that it fires at 01:00 (G-5 A rules out clock
simulation). Contrasts run the shipped image's scheduler on a planted schedule file, or in another
zone, with no network: it must refuse to start, so no table is loaded and the check fails.
"""

import subprocess
import time
import uuid
from pathlib import Path

import pytest

from tests.runtime.backup_lab import (
    BackupLab,
    complete_sets,
    failure_fields,
    failure_lines,
    schedule_command,
    set_names,
)
from tests.runtime.lab import docker

pytestmark = pytest.mark.runtime

LOADED = "/run/eko-backup/loaded-schedule"
# Synthetic values for the start-up check only; nothing is contacted (--network none).
OFFLINE_NAMES = (
    "BACKUP_DB_PASSWORD",
    "BACKUP_DESTINATION_CREDENTIAL",
    "BACKUP_ENCRYPTION_PUBLIC_KEY",
    "BACKUP_DESTINATION",
    "BACKUP_DESTINATION_HOST_KEY",
    "MIGRATION_ADVISORY_LOCK_KEY",
    "BACKUP_MANIFEST_BACKEND_IMAGE",
    "BACKUP_MANIFEST_KEYCLOAK_IMAGE",
    "BACKUP_MANIFEST_POSTGRES_IMAGE",
)
OFFLINE_ENV = dict.fromkeys(OFFLINE_NAMES, "synthetic-offline")


def schedule_problems(loaded: str | None) -> list[str]:
    """The loaded table: exactly one entry, daily at 01:00, zone UTC, K-01's run command."""
    if not loaded:
        return ["no schedule table is loaded"]
    entries = [line.split() for line in loaded.splitlines() if line.strip()]
    if len(entries) != 1:
        return [f"{len(entries)} entries"]
    [entry] = entries
    expected = ["time=01:00", "zone=UTC", "command=" + " ".join(schedule_command())]
    fields = [entry[0], entry[1], " ".join(entry[2:])]
    return [] if fields == expected else [f"entry {fields}, not {expected}"]


def loaded_table(backup_lab: BackupLab) -> bool:
    probe = ("exec", "-T", "backup", "test", "-s", LOADED)
    return backup_lab.composition.compose(*probe, check=False).returncode == 0


def test_k05_the_scheduler_has_loaded_one_daily_entry_at_0100_utc(backup_lab: BackupLab) -> None:
    composition = backup_lab.composition
    composition.compose("up", "-d", "--no-deps", "backup")
    backup_lab.wait_until("the scheduler wrote its loaded table", lambda: loaded_table(backup_lab))
    pid_one = composition.compose("exec", "-T", "backup", "cat", "/proc/1/cmdline").stdout
    program, argument = pid_one.split("\0")[-3:-1]
    assert (program.rsplit("/", 1)[-1], argument) == ("eko-backup", "schedule"), pid_one
    loaded = composition.compose("exec", "-T", "backup", "cat", LOADED).stdout
    assert schedule_problems(loaded) == []
    assert composition.compose("exec", "-T", "backup", "date", "+%Z").stdout.strip() == "UTC"
    logs = composition.compose("logs", "--no-color", "backup").stdout
    assert "eko-backup: schedule loaded " + loaded.strip() in logs


def planted_image(backup_lab: BackupLab, tmp_path: Path, schedule: str) -> str:
    base = backup_lab.backup_image()
    (tmp_path / "schedule").write_text(schedule, encoding="utf-8", newline="")
    (tmp_path / "Dockerfile").write_text(
        f"FROM {base}\nCOPY schedule /etc/eko-backup/schedule\n", encoding="utf-8"
    )
    tag = f"localhost/eko-crm/backup-planted:{tmp_path.name.lower()}"
    docker("build", "-q", "-t", tag, str(tmp_path), timeout=600)
    backup_lab.images[tag] = tag
    return tag


def offline_scheduler(image: str, *env: str) -> subprocess.CompletedProcess[str]:
    arguments = [item for name, value in OFFLINE_ENV.items() for item in ("-e", f"{name}={value}")]
    for pair in env:
        arguments += ["-e", pair]
    # Named, and removed in any case: a scheduler that does not refuse keeps running after the
    # timeout fails the test (QA, EKO-1-14: two such containers outlived a mutation run).
    name = f"bkp-offline-{uuid.uuid4().hex[:10]}"
    try:
        return docker(
            "run", "--rm", "--name", name, "--network", "none", *arguments, image,
            check=False, timeout=60,
        )  # fmt: skip
    finally:
        docker("rm", "-f", name, check=False)


@pytest.mark.parametrize(
    "schedule",
    [
        "01:00 Europe/Warsaw eko-backup run\n",
        "01:00 UTC eko-backup run\n13:00 UTC eko-backup run\n",
        "# no entry\n",
        "01:00 UTC eko-backup run\r\n",
    ],
    ids=["warsaw-entry", "two-entries", "no-entry", "crlf-entry"],
)
def test_k05_contrast_a_planted_schedule_is_refused(
    backup_lab: BackupLab, tmp_path: Path, schedule: str
) -> None:
    backup_lab.composition.compose("up", "-d", "--no-deps", "backup")
    result = offline_scheduler(planted_image(backup_lab, tmp_path, schedule))
    assert result.returncode != 0
    [line] = failure_lines(result.stderr)
    assert failure_fields(line)["reason"] == "schedule"
    assert schedule_problems(None) != []


def test_k05_contrast_the_scheduler_refuses_the_warsaw_zone(backup_lab: BackupLab) -> None:
    composition = backup_lab.composition
    composition.compose("up", "-d", "--no-deps", "backup")
    image = backup_lab.backup_image()
    result = offline_scheduler(image, "TZ=Europe/Warsaw")
    assert result.returncode != 0
    [line] = failure_lines(result.stderr)
    assert failure_fields(line)["reason"] == "schedule"


# R-03 (fix round 1): a scheduler a test starts never outlives that test, so a session that spans
# 01:00 UTC gets no real run in the middle of other tests. The pair runs in file order.


def test_r03_a_test_starts_the_scheduler(backup_lab: BackupLab) -> None:
    backup_lab.scheduler()
    assert backup_lab.scheduler_running()


def test_r03_the_next_test_finds_no_scheduler_running(backup_lab: BackupLab) -> None:
    assert not backup_lab.scheduler_running()


# The scheduler loop (Reviewer, "tests I couldn't break"): the shipped scheduler with a schedule
# file whose entry is two minutes ahead fires exactly one run, in that UTC minute. Only the data
# file differs from the shipped image; the zone check makes local time and UTC the same clock in
# the container, so comparing local time instead of `date -u` is an equivalent mutant.


def test_k05_the_scheduler_fires_one_run_in_its_entrys_minute(
    backup_lab: BackupLab, tmp_path: Path
) -> None:
    backup_lab.at_probe_head()
    [[now]] = backup_lab.sql("SELECT to_char(now() AT TIME ZONE 'UTC', 'HH24:MI:SS')")
    hour, minute, second = (int(part) for part in now.split(":"))
    ahead = (hour * 60 + minute + (2 if second < 40 else 3)) % (24 * 60)
    entry = f"{ahead // 60:02d}:{ahead % 60:02d}"
    tag = planted_image(backup_lab, tmp_path, f"{entry} UTC eko-backup run\n")
    planted = backup_lab.with_backup_image(tag)
    before = set_names(backup_lab.double)
    planted.compose("up", "-d", "--no-deps", "backup")
    try:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            [[current]] = backup_lab.sql("SELECT to_char(now() AT TIME ZONE 'UTC', 'HH24:MI')")
            if (
                current not in (entry, *previous_minutes(entry))
                and not backup_lab.backup_sessions()
            ):
                break
            time.sleep(5)
        logs = planted.compose("logs", "--no-color", "backup").stdout
    finally:
        planted.compose("rm", "-s", "-f", "backup", check=False)
    succeeded = [line for line in logs.splitlines() if "eko-backup: run succeeded " in line]
    assert len(succeeded) == 1, logs[-3000:]
    new = set_names(backup_lab.double) - before
    assert len(new) == 1 and new <= complete_sets(backup_lab.double)
    [name] = new
    assert name[13:17] == entry.replace(":", ""), (name, entry)


def previous_minutes(entry: str) -> tuple[str, ...]:
    """The minutes before the entry's, while the test waits for it."""
    hour, minute = (int(part) for part in entry.split(":"))
    total = hour * 60 + minute
    return tuple(f"{(total - k) % 1440 // 60:02d}:{(total - k) % 60:02d}" for k in (1, 2, 3))
