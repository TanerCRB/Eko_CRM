"""EKO-1-12 QA contrast (gate 2): the proxy gate is its boot-bound markers, per gate, and
open_gate's verification is load-bearing.

The fail-closed mechanism (ADR-0004 addendum of 2026-11-02 at the criterion level, extended
by the verification control ADR-0004-C34 of the addendum of 2026-11-06 — printed "C29" there,
renumbered by the dated correction of 2026-11-10 — and bound to the running boot by
ADR-0004-C33 of that correction; this file is QA's independent contrast, not a restatement):

- `proxy/entrypoint.sh` selects `Caddyfile.closed` — a configuration with no listener at all —
  unless `/data/admin-open` / `/data/public-open` markers exist AND each marker's content is
  the boot token the proxy reads for the running Keycloak container (a per-boot UUID the
  Keycloak entrypoint wrapper rotates as its first act, ADR-0004-C33), and refuses to start
  with the public marker while the admin marker is absent.
- `scripts/keycloak-bootstrap.sh` removes both markers at start; `open_gate` records each
  gate's marker bound to the verified boot only after that gate's own preconditions, verifies
  with an in-container wget that the listener actually serves, and removes the marker again
  (re-closing the proxy) when that verification fails, recording the residual state.
- The Keycloak entrypoint wrapper's own precondition, carried by the last test here: a
  container start that cannot rotate the boot token dies before Keycloak launches — a
  loud, fail-closed refusal, never a silent unrotated boot.

What each phase carries — and, from the executed EKO-1-12/qa2-* mutations, what it does not
(QA round-2 finding F-03: a contrast that survives a mutation is not protection for that
mechanism, and this file must not read as if it were).

1. Composition brought up without the bootstrap: both listeners are closed at the connection
   level (socket death — no TLS handshake completes, not a 2xx/5xx behind a bound listener),
   and a fresh volume carries no markers. NOT a carrier of the entrypoint's marker
   selection: `prepare` keeps Keycloak out of the bring-up, so even an entrypoint always
   selecting the full Caddyfile leaves the upstream unreachable and the connection still
   dies at the transport level — this contrast PASSED under the EKO-1-12/qa2-9a always-open
   mutation. It pins the fail-closed end state every other phase contrasts against, not the
   mechanism that selects it.
2. Carrier of the entrypoint's marker selection and boot-identity comparison. Marker gating
   per gate, marker content as the gate's second half: a blind empty touch does NOT open (it
   names no boot); the admin marker written with the current boot identity opens exactly the
   admin listener while the auth listener stays connection-dead. Phases 1-2 of this test,
   `test_k02_markers_are_bound_to_the_current_keycloak_boot` and phase 3 below are the file
   set that carries the marker mechanism: this test FAILED under the dropped identity
   comparison (EKO-1-12/qa2-3, once the blind-touch phase was hardened against the
   restart bind race — finding F-04) and under the always-open entrypoint (qa2-9a).
   Dropping the marker write kills the second half.
3. The executed carrier of `open_gate`'s reachability verification and of its marker
   cleanup on failure — of the contrasts run under those mutations, only this phase changed
   color. With the admin listener unable to serve (broken `Caddyfile.admin` inside the
   proxy container), the bootstrap must exit non-zero, must not record either gate as open,
   must remove the marker of the gate it could not verify (R-06's residual state), and must
   keep the auth listener closed. Skipping the wget verification — touching the marker
   blindly and always returning success — lets the bootstrap proceed, write the public
   marker too, and open the auth listener on a composition whose admin gate never actually
   served: this phase kills that mutation twice (exit code and closed auth listener,
   EKO-1-12/qa2-4) and killed the rm-on-fail removal (qa2-5). The K-02 precondition
   contrasts do NOT carry the verification: they abort before `open_gate` runs and PASSED
   under qa2-4 — see the docstring of test_eko112_k02_bootstrap_order.py.
"""

import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    BOOT_IDENTITY,
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
    # Wait until the proxy is actually running before asserting death: during the restart
    # window Caddy has not bound yet and a refused connection would look like the closed
    # gate even under an entrypoint that honors bare markers (found by the EKO-1-12/qa2-3
    # mutation, which survived the original instant-after-restart assertion).
    deadline = time.monotonic() + 30.0
    started: dict[str, object] = {}
    while time.monotonic() < deadline:
        started = fresh.inspect("proxy")["State"]
        if started.get("Running") and started.get("ExitCode") == 0:
            break
        time.sleep(1.0)
    time.sleep(3.0)  # let Caddy bind whatever configuration the entrypoint selected
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


def test_qa_keycloak_start_that_cannot_rotate_the_token_dies_loudly(
    fresh: Composition, tmp_path: Path
) -> None:
    """C33's wrapper precondition, carried offline on the real composition.

    The honest variant named in the brief for "stub the wrapper rotation": rather than
    re-implementing the entrypoint command, the token directory is made unwritable for
    the Keycloak container's own user (uid 1000), so the REAL wrapper's first act fails
    on the REAL composition. The claim carried: a start that cannot rotate dies before
    `kc.sh` runs (the refusal line, not a Keycloak banner, is all the log ever shows);
    the full bootstrap then fails closed at its own `up --wait` (exit non-zero), the
    markers it wiped at its start stay absent, both listeners are connection-dead and
    the helper reads no token. A silently unrotated boot would pass this phase with
    Keycloak serving and the gates open. Removing the wrapper's refusal exit, or
    rotating into an unprotected path, turns this test green-false — QA's mutation
    target; against the withdrawn ARP primitive this scenario did not even exist (the
    identity was never written by Keycloak at all)."""
    prepare(fresh)
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")
    # The boot carrier exists at this point, seeded by the proxy's first attach (the same
    # one-off docker-run technique `open_gate` uses for marker removal after a crash-loop):
    # hand the volume root to uid 0 and refuse writes to uid 1000.
    tag = f"{fresh.project}-proxy:latest"
    reseed = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{fresh.project}_keycloak-boot:/mnt",
            "--entrypoint", "sh", tag, "-c",
            "chown -R 0:0 /mnt && chmod 755 /mnt",
        ],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert reseed.returncode == 0, reseed.stderr[-500:]
    result = run_bootstrap(fresh, tmp_path / "bootstrap-no-rotate.jsonl", expected=1)
    assert result.returncode == 1
    logs = fresh.compose("logs", "--tail", "400", "keycloak", check=False)
    text = logs.stdout + logs.stderr
    assert "boot token could not be rotated" in text, (
        f"the unrotatable Keycloak start did not refuse loudly: {text[-2000:]}"
    )
    assert "Keycloak 26" not in text, "kc.sh started although the rotation refused"
    assert marker_value(fresh, "admin") == ""
    assert marker_value(fresh, "public") == ""
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")
    assert boot_identity(fresh) == "", (
        "the helper observed a boot token on a composition whose rotation was refused"
    )


def test_qa_boot_carrier_seeds_keycloak_writable_ownership_in_either_attach_order(
    fresh: Composition,
) -> None:
    """The seeded-ownership claim of the 2026-11-10 addendum, executed on the real
    composition in the order no other test fixes: Keycloak attaches the empty volume
    FIRST.

    `prepare` brings the proxy up without Keycloak, so every other run in this set
    exercises proxy-first seeding (and its keycloak rotation proves that volume root
    writable by uid 1000). Here the reverse order runs: `up -d --wait keycloak` keeps
    the proxy out of the bring-up, the volume root is seeded by the IDENTITY image, and
    the wrapper's rotation succeeding under uid 1000 is the writability proof for that
    seed. The proxy then attaches the already-initialized volume read-only and its
    helper must read the same token. The observed ownership modes are recorded in
    docs/evidence/EKO-1-12/fix-round-2-boot-identity.md; if the daemon inherited a
    root-owned volume root despite the seed, this test is where it turns red.
    """
    fresh.compose(
        "up", "-d", "--wait", "--wait-timeout", "600", "keycloak", timeout=700
    )  # fmt: skip
    root = fresh.compose(
        "exec", "-T", "keycloak", "stat", "-c", "%u %g %a", "/etc/eko/keycloak-boot"
    ).stdout.strip()
    assert root == "1000 1000 755", (
        f"keycloak-first seeding did not leave a keycloak-usable volume root: {root!r}"
    )
    # The rotation ran as the first act of this start, in a directory the identity
    # image seeded: proof of writability, not of a permissive default.
    token = fresh.compose(
        "exec", "-T", "keycloak", "cat", "/etc/eko/keycloak-boot/token"
    ).stdout.strip()
    assert BOOT_IDENTITY.fullmatch(token), (
        f"no rotated boot token on the keycloak-first volume: {token!r}"
    )
    seed = fresh.compose(
        "exec", "-T", "keycloak", "cat", "/etc/eko/keycloak-boot/.seed", check=False
    ).stdout.strip()
    assert seed and not BOOT_IDENTITY.fullmatch(seed), (
        "the seed placeholder is absent or indistinguishable from a real token"
    )
    # Proxy second: its image's seed is inert on the initialized volume; the helper
    # reads the Keycloak-seeded token through the read-only mount.
    fresh.compose(
        "up", "-d", "--wait", "--wait-timeout", "600", "proxy", timeout=700
    )  # fmt: skip
    seen = boot_identity(fresh)
    assert seen == token, f"the proxy helper read {seen!r} where the carrier holds {token!r}"
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")
