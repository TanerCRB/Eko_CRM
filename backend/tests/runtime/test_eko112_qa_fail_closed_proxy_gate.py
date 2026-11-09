"""EKO-1-12 QA contrast (gate 2): the proxy gate is its boot-bound markers, per gate, and
open_gate's verification is load-bearing.

The fail-closed mechanism (ADR-0004 addendum of 2026-11-02 at the criterion level, extended
by the 2026-11-06 C29 addendum the fix round implements; this file is QA's independent
contrast, not a restatement):

- `proxy/entrypoint.sh` selects `Caddyfile.closed` — a configuration with no listener at all —
  unless `/data/admin-open` / `/data/public-open` markers exist AND each marker's content is
  the boot identity the proxy observes for the running Keycloak container (assigned per
  container creation), and refuses to start with the public marker while the admin marker is
  absent.
- `scripts/keycloak-bootstrap.sh` removes both markers at start; `open_gate` records each
  gate's marker bound to the verified boot only after that gate's own preconditions, verifies
  with an in-container wget that the listener actually serves, and removes the marker again
  (re-closing the proxy) when that verification fails, recording the residual state.

What each test pins:

1. Composition brought up without the bootstrap: both listeners are closed at the connection
   level (socket death — no TLS handshake completes, not a 2xx/5xx behind a bound listener).
   Removing the marker selection from `proxy/entrypoint.sh` (always the full Caddyfile) turns
   this into served-502/503 responses and kills the test.
2. Marker gating per gate, and marker content as the gate's second half: a blind empty touch
   does NOT open (it names no boot); the admin marker written with the current boot identity
   opens exactly the admin listener while the auth listener stays connection-dead. Dropping
   the entrypoint's identity comparison makes the blind touch serve and kills the test
   (R-05/S-03); dropping the marker write kills the second half.
3. `open_gate`'s verification is what stops the bootstrap before the later gate: with the
   admin listener unable to serve (broken `Caddyfile.admin` inside the proxy container), the
   bootstrap must exit non-zero, must not record either gate as open, must remove the marker
   of the gate it could not verify (R-06's residual state), and must keep the auth listener
   closed. Skipping the wget verification — touching the marker blindly and always returning
   success — lets the bootstrap proceed, write the public marker too, and open the auth
   listener on a composition whose admin gate never actually served: this test kills that
   mutation twice (exit code and closed auth listener).
"""

import time
from pathlib import Path

import httpx
import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    boot_identity,
    listener_open,
    marker_value,
    prepare,
    run_bootstrap,
    write_gate_marker,
)

pytestmark = pytest.mark.runtime

OPENID_PATHS = {
    "admin": "/realms/master/.well-known/openid-configuration",
    "auth": "/realms/eko/.well-known/openid-configuration",
}


def assert_connection_death(composition: Composition, listener: str) -> str:
    """The listener must fail at the transport level; any HTTP response means it is bound."""
    try:
        response = composition.through_proxy(listener, OPENID_PATHS[listener])
    except httpx.TransportError as error:
        return f"{type(error).__name__}: {error}"
    raise AssertionError(
        f"the {listener} listener answered HTTP {response.status_code} — it is bound and "
        "serving; fail-closed requires the connection itself to die, not a status code"
    )


def wait_for_serving(composition: Composition, listener: str, deadline_seconds: int = 90) -> int:
    """Poll until the listener answers with a real HTTP status (any status: it is bound)."""
    deadline = time.monotonic() + deadline_seconds
    last_failure = "not attempted"
    while time.monotonic() < deadline:
        try:
            response = composition.through_proxy(listener, OPENID_PATHS[listener])
        except httpx.TransportError as error:
            last_failure = f"{type(error).__name__}: {error}"
            time.sleep(2.0)
            continue
        return response.status_code
    raise AssertionError(f"the {listener} listener never became reachable: {last_failure}")


@pytest.fixture
def bootstrap_broken_proxy(fresh: Composition) -> Composition:
    """`prepare` the composition, then make `Caddyfile.admin` unparseable inside the proxy.

    The proxy is running the closed configuration at this point (no markers on the fresh
    `proxy-data` volume), so nothing crashes yet. The broken file only takes effect when the
    bootstrap's `open_gate` writes the admin marker and restarts the proxy — the exact moment
    the gate's own verification must notice that the listener does not serve.
    """
    prepare(fresh)
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")
    fresh.compose(
        "exec", "-T", "-u", "0", "proxy", "sh", "-c",
        "printf '%s\\n' 'qa-contrast-broken {' '	unrecognized_directive_x' '}' "
        "> /etc/caddy/Caddyfile.admin",
    )  # fmt: skip
    return fresh


def test_qa_both_listeners_are_closed_without_the_bootstrap(fresh: Composition) -> None:
    """K-02 fail-closed contrast: bare bring-up opens no listener at the connection level."""
    prepare(fresh)
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")
    assert not listener_open(fresh, "admin")
    assert not listener_open(fresh, "auth")
    markers = sorted(fresh.compose("exec", "-T", "proxy", "ls", "/data").stdout.split())
    assert "admin-open" not in markers, f"admin marker present on a fresh volume: {markers}"
    assert "public-open" not in markers, f"public marker present on a fresh volume: {markers}"


def test_qa_admin_marker_opens_only_the_admin_listener(fresh: Composition) -> None:
    """The marker is the gate, gate by gate — and a marker that names no current Keycloak
    boot is not an open gate (R-05/S-03): admin alone must leave auth connection-dead."""
    prepare(fresh)
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")
    fresh.compose(
        "up", "-d", "--wait", "--wait-timeout", "600", "keycloak", timeout=700
    )  # fmt: skip
    # Keycloak serves, but with no marker the entrypoint still runs Caddyfile.closed.
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")

    # The blind touch is not a gate: an empty marker names no boot, so the entrypoint
    # keeps every listener closed. Removing the entrypoint's identity comparison makes
    # this phase serve instead and kills the test.
    fresh.compose("exec", "-T", "proxy", "touch", "/data/admin-open")
    fresh.compose("restart", "proxy")
    _ = fresh.inspect("proxy")["State"]  # the restart is synchronous; the container is up
    assert_connection_death(fresh, "admin")

    identity = boot_identity(fresh)
    assert identity, "the proxy cannot observe the current Keycloak boot identity"
    write_gate_marker(fresh, "admin", identity)
    fresh.compose("restart", "proxy")
    status = wait_for_serving(fresh, "admin")
    assert status == 200, f"admin listener answered {status} after its own marker"
    assert_connection_death(fresh, "auth")

    # The guard half: the public marker without the admin marker refuses the proxy outright.
    fresh.compose(
        "exec", "-T", "proxy", "sh", "-c",
        "rm -f /data/admin-open; touch /data/public-open",
    )  # fmt: skip
    fresh.compose("restart", "proxy", check=False)
    refused = False
    state: dict[str, object] = {}
    logs_text = ""
    for _ in range(40):
        state = fresh.inspect("proxy")["State"]
        logs = fresh.compose("logs", "--tail", "10", "proxy", check=False)
        logs_text = logs.stdout + logs.stderr
        # `restart: unless-stopped` keeps Docker reporting the crash-looping container as
        # Running between attempts; the entrypoint's own exit code and guard message are the
        # signal that the public marker without the admin gate refuses to serve at all.
        if state["ExitCode"] == 1 and "requires the admin bootstrap gate" in logs_text:
            refused = True
            break
        time.sleep(1.0)
    assert refused, (
        "the proxy did not refuse the public marker without the admin gate; "
        f"final state: {state}; recent logs: {logs_text[-500:]}"
    )
    assert_connection_death(fresh, "auth")


def test_qa_open_gate_verification_stops_the_bootstrap_before_the_next_gate(
    bootstrap_broken_proxy: Composition, tmp_path: Path
) -> None:
    """The wget verification inside open_gate is what keeps the auth listener closed when the
    admin gate cannot actually serve; skipping it must let the blind touches through."""
    composition = bootstrap_broken_proxy
    evidence = tmp_path / "bootstrap-contrast.jsonl"
    result = run_bootstrap(composition, evidence, expected=1)
    assert "did not become reachable" in result.stderr, (
        f"the bootstrap did not fail at the gate verification:\n{result.stderr[-2000:]}"
    )
    events = [line for line in evidence.read_text(encoding="utf-8").splitlines() if line]
    assert any("custom provider selected" in line for line in events), (
        "the pre-listener provider verification did not run: the contrast scenario is broken"
    )
    assert any("filtering verified" in line for line in events), (
        "the live filtering verification did not run: the contrast scenario is broken"
    )
    assert not any("admin listener open" in line for line in events), (
        "the bootstrap recorded an open admin listener that its own verification rejected"
    )
    assert not any("public listener open" in line for line in events), (
        "the bootstrap recorded the public gate open although the admin gate never served"
    )
    # R-06: the gate that failed verification removes its own marker, so the recorded
    # closed state and the wire agree, and a later proxy start cannot reopen on it. The
    # failure record names the residual state.
    assert marker_value(composition, "admin") == "", (
        "the failed admin gate left its marker on the volume"
    )
    assert any("marker removed" in line for line in events), (
        f"the bootstrap did not record the residual marker state: {events}"
    )
    assert_connection_death(composition, "auth")
