"""K-05, schedule: backup's own main process is a scheduler that has loaded exactly one daily
entry at 01:00 UTC, which runs the command K-01 runs, in a container whose zone is UTC.

The check proves the entry is loaded, not that it fires at 01:00 (G-5 A rules out clock
simulation). Contrasts run the shipped image's scheduler on a planted schedule file, or in another
zone, with no network: it must refuse to start, so no table is loaded and the check fails.
"""

import subprocess
from pathlib import Path

import pytest

from tests.runtime.backup_lab import BackupLab, failure_fields, failure_lines, schedule_command
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
    base = backup_lab.composition.inspect("backup")["Config"]["Image"]
    (tmp_path / "schedule").write_text(schedule, encoding="utf-8")
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
    return docker("run", "--rm", "--network", "none", *arguments, image, check=False, timeout=60)


@pytest.mark.parametrize(
    "schedule",
    [
        "01:00 Europe/Warsaw eko-backup run\n",
        "01:00 UTC eko-backup run\n13:00 UTC eko-backup run\n",
        "# no entry\n",
    ],
    ids=["warsaw-entry", "two-entries", "no-entry"],
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
    image = composition.inspect("backup")["Config"]["Image"]
    result = offline_scheduler(image, "TZ=Europe/Warsaw")
    assert result.returncode != 0
    [line] = failure_lines(result.stderr)
    assert failure_fields(line)["reason"] == "schedule"
