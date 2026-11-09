"""EKO-1-12 K-02 / ADR-0004 addendum 2026-11-06 (C29): each gate marker names the current
Keycloak boot, so a composition-level bring-up that skipped the bootstrap cannot serve.

The accepted addendum requires the selected custom factory and the required filtering to be
verified before either listener opens, on every fresh bootstrap, restart and restore. The
mechanism proven here is the composition half of that rule: `open_gate` records the marker's
value as the boot identity the proxy container itself observes for the running Keycloak, and
`proxy/entrypoint.sh` selects an open configuration only while the marker names that current
identity. Recreating the Keycloak container without running `scripts/keycloak-bootstrap.sh`
(new boot, unverified provider) therefore leaves both listeners closed at the connection level,
even after a proxy restart re-reads the persistent markers; a rerun of the bootstrap — which
re-verifies provider selection and filtering for the current boot — reopens them. Contrast the
stale-marker red (both listeners dead) against the reopen green; removing the identity check
from the entrypoint turns the stale-marker phase into served listeners and kills this test
(the QA entrypoint mutations apply to the same mechanism).

A same-container `docker compose restart keycloak` keeps the verified boot identity and the
listeners open (the accepted configuration, provider included, is unchanged); the invariant
C29 needs is that no listener ever serves a boot the bootstrap did not verify — which is
exactly what a container identity change means (the R-05/S-03 scenarios: image swap, force
recreate, any composition bring-up that creates a new Keycloak container).
"""

import time

import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    boot_identity,
    listener_open,
    marker_value,
    prepare,
    run_bootstrap,
)
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import assert_connection_death

pytestmark = pytest.mark.runtime

MARKER_GATES = ("admin", "public")


def wait_for_proxy_running(composition: Composition, seconds: int = 120) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = composition.inspect("proxy")["State"]
        if state.get("Running") and state.get("ExitCode") == 0:
            return
        time.sleep(1.0)
    raise AssertionError(
        f"the proxy did not reach a running state within {seconds}s: "
        f"{composition.inspect('proxy')['State']}"
    )


def test_k02_markers_are_bound_to_the_current_keycloak_boot(fresh: Composition) -> None:
    prepare(fresh)
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")

    identity = boot_identity(fresh)
    assert identity, "the proxy could not observe a Keycloak boot identity after a bootstrap"
    for gate in MARKER_GATES:
        assert marker_value(fresh, gate) == identity, (
            f"open_gate must record the current boot identity in /data/{gate}-open"
        )

    # The finding's scenario: an operator recreates Keycloak through the composition alone —
    # e.g. `compose up -d --build keycloak` after an image change — without ever running
    # scripts/keycloak-bootstrap.sh. The boot identity changes; nobody verifies the provider.
    fresh.compose(
        "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "600", "keycloak",
        timeout=700,
    )  # fmt: skip
    recreated = boot_identity(fresh)
    assert recreated and recreated != identity, (
        "the recreated Keycloak container kept the same boot identity: the contrast would "
        "exercise nothing (the marker could match a container nobody verified)"
    )

    # A later proxy start (host reboot, restart policy, or a plain restart) re-reads the
    # markers: they name the previous boot, so both listeners must stay closed.
    fresh.compose("restart", "proxy")
    wait_for_proxy_running(fresh)
    assert not listener_open(fresh, "admin"), "the admin listener served on a stale marker"
    assert not listener_open(fresh, "auth"), "the public listener served on a stale marker"
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")

    # The stale state is fail-closed, not a permanent lock: the bootstrap rerun re-verifies
    # the provider for the current boot and reopens both gates.
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")
    current = boot_identity(fresh)
    for gate in MARKER_GATES:
        assert marker_value(fresh, gate) == current, (
            f"the rerun left /data/{gate}-open naming a boot other than the current one"
        )
