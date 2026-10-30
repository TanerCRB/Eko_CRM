"""K-06 (ADR-0005 *What may appear in logs*): backup's log, on a successful and on a failed run,
holds the run's times, outcome and row counts, and never a row's content or a secret.

Every value searched for is unique to this lab: the markers, the role passwords, the destination
credential and the destination's host name (the double's network alias). The database service
name `postgres` is searched for only inside connection-string forms, because as a bare substring
it is also an image and a role name.
"""

import base64
import json
import re

import pytest

from tests.runtime.backup_lab import BackupLab, RunResult, open_set, set_names, unique_marker

pytestmark = pytest.mark.runtime

CONNECTION_STRING = re.compile(
    r"\b(?:postgres(?:ql)?|sftp|ssh)://|\b(?:host|hostaddr|port|user|password|dbname)\s*=\s*\S",
    re.IGNORECASE,
)
SUCCESS = re.compile(
    r"eko-backup: run succeeded set=(?P<set>\S+) started=(?P<started>\S+) ended=(?P<ended>\S+) "
    r"row_counts=(?P<counts>\{.*\})"
)
TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z")


def forbidden_values(backup_lab: BackupLab, markers: list[str]) -> list[str]:
    env = backup_lab.composition.env
    passwords = [value for name, value in env.items() if "PASSWORD" in name]
    credential = env["BACKUP_DESTINATION_CREDENTIAL"]
    key_body = base64.b64decode(credential).decode().splitlines()[1]
    return [*markers, *passwords, credential, key_body, backup_lab.double.alias]


def leaks(output: str, values: list[str]) -> list[str]:
    found = [f"value {index}" for index, value in enumerate(values) if value in output]
    return found + [m.group(0) for m in CONNECTION_STRING.finditer(output)]


@pytest.fixture(scope="module")
def runs(backup_lab: BackupLab) -> tuple[list[str], RunResult, RunResult, str]:
    backup_lab.at_probe_head()
    markers = [unique_marker("log-row"), unique_marker("log-user")]
    backup_lab.plant_row(markers[0])
    backup_lab.plant_keycloak_user(markers[1])
    before = set_names(backup_lab.double)
    succeeded = backup_lab.run()
    [name] = set_names(backup_lab.double) - before
    backup_lab.sql("REVOKE CONNECT ON DATABASE keycloak FROM eko_backup")
    try:
        failed = backup_lab.run()
    finally:
        backup_lab.sql("GRANT CONNECT ON DATABASE keycloak TO eko_backup")
    return markers, succeeded, failed, name


def test_k06_the_log_of_a_successful_and_a_failed_run_holds_no_content_or_secret(
    backup_lab: BackupLab, runs: tuple[list[str], RunResult, RunResult, str]
) -> None:
    markers, succeeded, failed, _ = runs
    assert succeeded.code == 0 and failed.code != 0
    values = forbidden_values(backup_lab, markers)
    assert leaks(succeeded.output, values) == []
    assert leaks(failed.output, values) == []


def test_k06_contrast_the_successful_runs_log_holds_times_outcome_and_counts(
    backup_lab: BackupLab, runs: tuple[list[str], RunResult, RunResult, str]
) -> None:
    _, succeeded, _, name = runs
    [match] = [m for line in succeeded.output.splitlines() if (m := SUCCESS.fullmatch(line))]
    assert match["set"] == name
    assert TIME.fullmatch(match["started"]) and TIME.fullmatch(match["ended"])
    assert match["started"] <= match["ended"]
    manifest = open_set(backup_lab.double, name, backup_lab.identity).manifest
    assert json.loads(match["counts"]) == manifest["row_counts"]


def test_k06_contrast_the_leak_scanner_finds_each_value_and_a_connection_string(
    backup_lab: BackupLab,
) -> None:
    values = forbidden_values(backup_lab, ["marker-x"])
    for value in values:
        assert leaks(f"line {value} line", values) != []
    for form in ("postgresql://eko_backup@postgres/eko", "host=postgres dbname=eko"):
        assert leaks(form, []) != []
