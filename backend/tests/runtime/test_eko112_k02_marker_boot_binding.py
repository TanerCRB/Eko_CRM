"""EKO-1-12 K-02 / ADR-0004-C33 (addendum 2026-11-10, replacing the ARP binding the
2026-11-06 addendum shipped): each gate marker names the current Keycloak boot, so a
composition-level bring-up that skipped the bootstrap cannot serve.

The verification requirement itself is ADR-0004-C34 (the 2026-11-06 control, renumbered by
the 2026-11-10 correction): the selected custom factory and the required filtering must be
verified before either listener opens, on every fresh bootstrap, restart and restore. The
mechanism proven here is the composition half of that rule under the boot binding C33
defines: `open_gate` records the marker's value as the boot token the running Keycloak
container rotated at its own current start (observed by the proxy through the same shipped
helper, as a pure file read), and `proxy/entrypoint.sh` selects an open configuration only
while the marker names that current boot. Recreating the Keycloak container without running
`scripts/keycloak-bootstrap.sh` (new boot, unverified provider) therefore leaves both
listeners closed at the connection level, even after a proxy restart re-reads the persistent
markers; a rerun of the bootstrap — which re-verifies provider selection and filtering for
the current boot — reopens them. Contrast the stale-marker red (both listeners dead) against
the reopen green; removing the identity check from the entrypoint turns the stale-marker
phase into served listeners and kills this test (the QA entrypoint mutations apply to the
same mechanism).

Boot means every Keycloak container start (the accepted 2026-11-10 semantic shift). The
final phase asserts the strengthened claim: a same-container `docker compose restart
keycloak` — no bootstrap — rotates the token, and the next proxy start finds both listeners
connection-dead until a bootstrap re-verifies the pair for the new boot. The earlier ARP-era
docstring claim that such a restart "keeps the verified boot identity and the listeners
open" is withdrawn by the addendum; its hardware-address observation keyed the identity to
container creation, so a reboot or restart re-opened listeners the bootstrap had never
re-verified. R-05/S-03 scenarios (image swap, force recreate, any bring-up that creates a
new container) stay covered by the phase above.
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


def wait_for_rotated_identity(composition: Composition, previous: str, seconds: int = 90) -> str:
    """Poll the helper's file read until it names a boot token other than `previous`.

    The Keycloak entrypoint wrapper rotates the token as the FIRST act of the start, before
    `kc.sh`, so a pure read turns fresh shortly after the container starts; the bound covers
    the stop-start window, not any resolution. An empty read at the deadline is its own
    failure (the carrier could not observe a token at all), distinct from the identity-
    unchanged failure the C33 assertion targets."""
    deadline = time.monotonic() + seconds
    current = ""
    while time.monotonic() < deadline:
        current = boot_identity(composition)
        if current and current != previous:
            return current
        time.sleep(1.0)
    assert current, f"the proxy observed no boot token within {seconds}s of the keycloak restart"
    raise AssertionError(
        f"the restarted Keycloak kept the boot token {previous!r}: the carrier would name "
        "an unrotated boot (C33 says every container start rotates)"
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

    # C33 semantic shift (2026-11-10 addendum): boot means EVERY Keycloak container start.
    # A same-container `compose restart keycloak` with no bootstrap rotates the token (the
    # wrapper's first act) and thereby invalidates the markers a verified bootstrap had just
    # written: the next proxy start must find BOTH listeners connection-dead, and only a
    # bootstrap rerun reopens them. Under the withdrawn ARP binding the outcome was
    # host-dependent — on the CI ubuntu runners the same container kept its hardware address
    # across a restart and the listeners kept serving (Issue #126: the hole this closes),
    # while this Docker Desktop host reassigns the MAC per start (probe recorded in the
    # fix-round-2 evidence), which is exactly why a network-observed identity cannot be the
    # gate anywhere. The token primitive closes the semantic by construction, on every host.
    fresh.compose("restart", "keycloak")
    restarted = wait_for_rotated_identity(fresh, current)
    assert restarted != current
    fresh.compose("restart", "proxy")
    wait_for_proxy_running(fresh)
    assert not listener_open(fresh, "admin"), (
        "the admin listener served after a keycloak restart no bootstrap verified"
    )
    assert not listener_open(fresh, "auth"), (
        "the public listener served after a keycloak restart no bootstrap verified"
    )
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")

    # Again fail-closed, not locked: the rerun re-verifies the provider for the rotated boot.
    # (The rerun itself recreates the Keycloak container, i.e. yet another start and yet
    # another rotation — the assertion is that markers name THAT newest current boot.)
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")
    after_restart = boot_identity(fresh)
    for gate in MARKER_GATES:
        assert marker_value(fresh, gate) == after_restart, (
            f"the post-restart rerun left /data/{gate}-open naming a previous boot"
        )
