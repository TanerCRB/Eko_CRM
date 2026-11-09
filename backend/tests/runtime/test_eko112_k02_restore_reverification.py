"""EKO-1-12 K-02 item 5 / ADR-0004-C29 (addendum 2026-11-06): the restore half of the
listener boundary, run against the real composition.

R-04 / G-04: the DoD and C29 require that after a restore through the accepted local backup
path, the selected custom factory and the required filtering are verified before either
listener opens. This test:

1. bootstraps a fresh composition, runs the documented on-demand backup (EKO-1-14 path) into
   the destination double, drops the Keycloak database and restores it from that set
   (superuser `pg_restore` — the restore side of the same accepted path);
2. reruns `scripts/keycloak-bootstrap.sh` (the existing-volume rerun path: the database is
   restored, the gate markers' own volume was not wiped) and asserts the recorded order:
   `custom provider selected` and `filtering verified` precede both listener-open events,
   and both listeners open only afterwards;
3. reads back restored state (realm and accounts exist through the reverified store);
4. observes the R-04 unknown: break-glass password divergence. With the same restored set,
   the environment file's `EKO112_BREAKGLASS_ONE_PASSWORD` is rotated before the rerun —
   the rerun then authenticates from the environment against the restored database and
   fails: exit code 1, and BOTH listeners stay closed (the rerun wiped the markers at its
   start and the admin gate never opened). The record states which branch the mechanism
   takes; restoring the environment value reopens both gates.

Nothing here deletes a volume: the damage is a `DROP DATABASE keycloak` inside this test's
own composition, undone by the accepted restore.
"""

import subprocess
import uuid
from pathlib import Path

import pytest

from tests.runtime.backup_lab import (
    backup_environment,
    complete_sets,
    open_set,
    set_names,
    start_double,
)
from tests.runtime.conftest import Composition, read_env, write_env
from tests.runtime.keycloak_client import (
    RealmClient,
    listener_open,
    prepare,
    run_bootstrap,
)
from tests.runtime.lab import docker
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import assert_connection_death
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime


def connection_closed(composition: Composition, listener: str) -> None:
    """A closed gate is the listener's connection dying at the transport, never a status
    code behind a bound socket (the QA gate probe's rule)."""
    assert not listener_open(composition, listener), f"the {listener} listener is open"
    assert_connection_death(composition, listener)


def run_documented_backup(composition: Composition) -> None:
    """The command documented in backup/README.md (`docker compose run --rm --no-deps backup
    eko-backup run`), executed against this composition."""
    name = f"eko112-restore-bkp-{uuid.uuid4().hex[:8]}"
    composition.compose(
        "run", "--rm", "--no-deps", "-T", "--name", name, "backup", "eko-backup", "run",
        timeout=600,
    )  # fmt: skip


def restore_keycloak_database(composition: Composition, dump: bytes) -> None:
    """Drop the Keycloak database (this composition's own data) and restore it from the
    accepted set's dump, as the documented restore does — superuser, stop-on-error."""
    composition.compose("stop", "keycloak", check=False)
    container = composition.container_id("postgres")
    terminate = subprocess.run(
        [
            "docker", "exec", container, "psql", "-U", "postgres", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", "-c",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'keycloak'",
        ],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    assert terminate.returncode == 0, terminate.stderr
    subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "DROP DATABASE keycloak",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    restored = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "pg_restore",
            "-U",
            "postgres",
            "--create",
            "--exit-on-error",
            "-d",
            "postgres",
        ],
        input=dump,
        capture_output=True,
        timeout=600,
    )
    assert restored.returncode == 0, restored.stderr.decode(errors="replace")[-2000:]


def events_order_pair(events: list[str]) -> tuple[int, int, int, int]:
    def position(fragment: str) -> int:
        return next(index for index, line in enumerate(events) if fragment in line)

    return (
        position("custom provider selected"),
        position("filtering verified"),
        position("admin listener open"),
        position("public listener open"),
    )


def test_k02_restore_reverifies_the_provider_before_listeners_open(
    fresh: Composition, tmp_path: Path
) -> None:
    double = start_double(fresh.project)
    identity, recipient = double.new_identity()
    try:
        values = read_env(fresh.env_file)
        # The double's host key, credential and base64 values carry spaces and +/=: quoted
        # for the bootstrap script's `.`-source of the environment file (compose's own
        # env-file parser strips the quotes again), so no value reaches the shell as a word.
        values.update(
            {name: f'"{value}"' for name, value in backup_environment(double, recipient).items()}
        )
        write_env(fresh.env_file, values)
        prepare(fresh)  # creates the project's default network the double joins below
        # Plain `docker network connect` (as backup_lab_session does): `compose network` is
        # not a compose command, and the project's network is a plain Docker object.
        docker("network", "connect", "--alias", double.alias,
               f"{fresh.project}_default", double.container)  # fmt: skip
        run_bootstrap(fresh)
        assert listener_open(fresh, "admin")
        assert listener_open(fresh, "auth")

        # Stop the service's own scheduler container (EKO-1-14's rule for tests that span
        # 01:00 UTC): the one-off documented run below needs the image, not the service.
        fresh.compose("rm", "-s", "-f", "backup", check=False)
        before = set_names(double)
        run_documented_backup(fresh)
        new_sets = complete_sets(double) - before
        assert new_sets, f"the on-demand backup produced no complete set at {sorted(before)}"
        set_name = sorted(new_sets)[-1]
        contents = open_set(double, set_name, identity)

        # Damage the live database, then restore it through the accepted path.
        restore_keycloak_database(fresh, contents.keycloak)

        evidence = tmp_path / "restore-rerun.jsonl"
        run_bootstrap(fresh, evidence)  # the existing-volume rerun path across the restore
        events = [line for line in evidence.read_text(encoding="utf-8").splitlines() if line]
        selected, verified, admin_open, public_open = events_order_pair(events)
        assert selected < verified < admin_open < public_open, (
            "after a restore the provider pair must precede both listener opens: "
            f"{selected} {verified} {admin_open} {public_open}"
        )
        assert "rerun existing volume live checks" in "".join(events)
        assert listener_open(fresh, "admin")
        assert listener_open(fresh, "auth")

        # Restored state is readable through the reverified store.
        master = RealmClient(fresh, "master")
        try:
            breakglass = master.direct_master_token(
                fixtures.ACCOUNTS["breakglass_one"],
                fresh.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
            )
            realm = master.admin_json(breakglass, "GET", "", realm="eko")
            assert realm["realm"] == "eko"
            accounts = master.admin_json(
                breakglass,
                "GET",
                "users",
                params={"username": fixtures.ACCOUNTS["administrator"], "exact": "true"},
                realm="eko",
            )
            assert len(accounts) == 1, "the restored realm lost the bootstrap administrator"
            events_body = master.admin_json(
                breakglass, "GET", "events", realm="eko", params={"max": "50"}
            )
            assert isinstance(events_body, list), "the restored event store is not readable"
        finally:
            master.close()

        # R-04 observation: divergence between the restored database and the environment's
        # break-glass password. Rotate the environment value only — the rerun authenticates
        # from the environment against the restored database.
        diverged = read_env(fresh.env_file)
        original = diverged[fixtures.PASSWORD_VARIABLES["breakglass_one"]]
        rotated = "synthetic-rotated-" + uuid.uuid4().hex
        diverged[fixtures.PASSWORD_VARIABLES["breakglass_one"]] = rotated
        write_env(fresh.env_file, diverged)
        divergence_evidence = tmp_path / "restore-divergence.jsonl"
        result = run_bootstrap(
            fresh, divergence_evidence, expected=1
        )  # fmt: skip
        assert result.returncode == 1
        # The divergent run dies at the master mode, before any accepted-state event is
        # recorded; the evidence file may therefore be absent or empty — both read as
        # "neither gate was recorded open".
        raw = (
            divergence_evidence.read_text(encoding="utf-8") if divergence_evidence.exists() else ""
        )
        events = [line for line in raw.splitlines() if line]  # fmt: skip
        assert not any("admin listener open" in line for line in events), (
            "the divergent restore rerun opened the admin gate"
        )
        assert not any("public listener open" in line for line in events), (
            "the divergent restore rerun opened the public gate"
        )
        connection_closed(fresh, "admin")
        connection_closed(fresh, "auth")

        # Not a permanent lock: the matching environment reopens everything through the
        # accepted pair.
        restored_env = read_env(fresh.env_file)
        restored_env[fixtures.PASSWORD_VARIABLES["breakglass_one"]] = original
        write_env(fresh.env_file, restored_env)
        run_bootstrap(fresh)
        assert listener_open(fresh, "admin")
        assert listener_open(fresh, "auth")
    finally:
        docker("rm", "-f", double.container, check=False)
        docker("rmi", "-f", f"localhost/eko-crm/backup-double:{fresh.project}", check=False)
