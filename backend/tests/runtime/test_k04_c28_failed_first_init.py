"""R-01 / ADR-0004 2026-10-28 C28 addendum, on the real `up` path with its restart policy.

"A volume whose first initialisation failed is removed before the next start, never started
again." A whitespace-only role password passes Compose's `:?` and is refused by the init content,
so the first initialisation fails after `initdb` has written the data directory. The restart
policy then starts the container again on that volume; it must not come up.
"""

import json
import subprocess
import time
from typing import Any

import pytest

from tests.runtime.conftest import Composition, read_env, write_env

pytestmark = pytest.mark.runtime

UP_SECONDS = 90
RESTARTED_SECONDS = 120
PLAIN_IMAGE = "postgres:18.6-trixie"


def postgres_state(composition: Composition) -> dict[str, Any]:
    state: dict[str, Any] = composition.inspect("postgres")["State"]
    return state


def wait_for_restarts(composition: Composition, seconds: int) -> int:
    deadline = time.monotonic() + seconds
    count = 0
    while time.monotonic() < deadline:
        count = int(composition.inspect("postgres")["RestartCount"])
        if count >= 2:
            break
        time.sleep(2)
    return count


def databases_on_volume(volume: str, password: str) -> set[str]:
    """Start the plain image (no guard, init skipped on a non-empty volume) to read the catalog."""
    started = subprocess.run(
        ["docker", "run", "-d", "--rm", "-v", f"{volume}:/var/lib/postgresql",
         "-e", f"POSTGRES_PASSWORD={password}", PLAIN_IMAGE],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    container = started.stdout.strip()
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            probe = subprocess.run(
                ["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True,
            )
            if probe.returncode == 0:
                break
            time.sleep(1)
        listed = subprocess.run(
            ["docker", "exec", container, "psql", "-U", "postgres", "-AtX",
             "-c", "SELECT datname FROM pg_database"],
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        return set(listed.stdout.split())
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


def test_k04_c28_failed_first_init_volume_is_never_started_again(fresh: Composition) -> None:
    values = read_env(fresh.env_file)
    # Quoted so the env file keeps it: whitespace-only passes `:?`, the init content refuses it.
    values["KEYCLOAK_DB_PASSWORD"] = '"   "'
    write_env(fresh.env_file, values)

    first = fresh.compose(
        "up", "-d", "--wait", "--wait-timeout", str(UP_SECONDS), "postgres",
        check=False, timeout=UP_SECONDS + 120,
    )  # fmt: skip
    assert first.returncode != 0, "postgres became healthy on a failed first initialisation"
    assert wait_for_restarts(fresh, RESTARTED_SECONDS) >= 1, "the restart policy did not apply"
    assert postgres_state(fresh).get("Health", {}).get("Status") != "healthy"
    logs = fresh.compose("logs", "postgres", check=False).stdout
    assert "KEYCLOAK_DB_PASSWORD" in logs
    assert "first initialisation did not complete" in logs

    # Correcting the environment file does not revive the volume either.
    values["KEYCLOAK_DB_PASSWORD"] = "synthetic-corrected-" + json.dumps(time.time())
    write_env(fresh.env_file, values)
    again = fresh.compose(
        "up", "-d", "--wait", "--wait-timeout", str(UP_SECONDS), "postgres",
        check=False, timeout=UP_SECONDS + 120,
    )  # fmt: skip
    assert again.returncode != 0, "a volume whose first initialisation failed started again"

    fresh.compose("stop", "postgres", check=False)
    found = databases_on_volume(f"{fresh.project}_pgdata", values["POSTGRES_PASSWORD"])
    assert {"eko", "keycloak"} & found == set()
