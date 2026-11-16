"""EKO-1-12 / Issue #126, QA4 finding Q4-1: `proxy/keycloak-boot-identity.sh` validates the
boot token it reads — the lower-case-hex-and-hyphen alphabet AND the exact UUID segment
lengths 8-4-4-4-12 — and this file carries that validation THROUGH the real container path,
so the qa4-5 mutation (removing the segment-length loop) turns it red.

Why the path is the real one: the helper is shipped inside the proxy image
(`proxy/Dockerfile` copies it to /usr/local/bin/eko-keycloak-boot-identity.sh) and is the
observation both gate callers make — `proxy/entrypoint.sh` compares each marker against its
stdout, and `scripts/keycloak-bootstrap.sh`'s `keycloak_boot_identity` is literally
`compose exec -T proxy sh /usr/local/bin/eko-keycloak-boot-identity.sh`. A malformed-shape
test against the host file would prove nothing about what the composition runs.

Mechanics: one fresh composition is brought to the full open state by the real bootstrap
(module-scoped: the bootstrap costs minutes, a proxy restart costs seconds, and the time
budget says batch all shapes on one composition; the module scope is also what lets a `-k`
mutation subset run just the length shapes against that one bring-up). A one-off `docker run`
of the Keycloak image ITSELF, uid 1000 (the rotation's own user) — the file's content is the
only thing changed, the writer identity matches the real rotation — mounts
`<project>_keycloak-boot` rw at /mnt and replaces /mnt/token (the same file the entrypoint
wrapper renames over) with each malformed shape. `compose restart proxy` then makes the
entrypoint and the bootstrap's identity path consume the observation.

What is asserted per shape, and which assertion carries the mutation:
1. the identity path refuses — `compose exec -T proxy sh <helper>` exits non-zero with EMPTY
   stdout (and the refused value never reaches stderr). THIS is the assertion qa4-5 flips:
   with the segment loop gone the six `len-` shapes (valid alphabet, wrong lengths) are
   printed as if they named a boot.
2. both listeners are connection-dead — fail-closed at the transport level, not a status
   code. On the mutation the listeners stay dead even for the `len-` shapes (the markers
   still name the real boot, which the written shape is not), so assertion 2 is the
   integration context, not the discriminator; assertion 1 is what must not be empty.
3. both markers still name the live boot — the closure came from the refused observation,
   not from marker state the test disturbed.

Branch honesty (residual gaps this file does NOT close): only the six `len-` ids flip red
under qa4-5. The four `alpha-` ids (MAC — the withdrawn ARP-era primitive's own shape,
uppercase hex, a shell-injection suffix, a two-line file) are refused by the alphabet case
check, which qa4-5 keeps; they carry the alphabet branch against a case-check mutation, and
the `-s`/missing-file branch stays carried by the rotation-refusal test in
test_eko112_qa_fail_closed_proxy_gate.py — that carrier is untouched here.

The final control closes the loop that a refusal could be an artifact of a broken
composition: with a fresh VALID UUID written by the same one-off and markers rewritten to
name it (`write_gate_marker`, the same primitive `open_gate` uses), the helper prints exactly
that token and both listeners serve again — fail-closed, never locked. Every synthetic
identifier; no credential, host address or real value appears anywhere.
"""

import subprocess
import time
import uuid
from collections.abc import Iterator

import pytest

from tests.runtime.conftest import Composition, new_composition
from tests.runtime.keycloak_client import (
    BOOT_IDENTITY,
    IDENTITY_SCRIPT,
    boot_identity,
    marker_value,
    prepare,
    run_bootstrap,
    write_gate_marker,
)
from tests.runtime.test_eko112_k02_marker_boot_binding import wait_for_proxy_running
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import (
    assert_connection_death,
    wait_for_serving,
)

pytestmark = pytest.mark.runtime

MARKER_GATES = ("admin", "public")

# Valid alphabet, wrong segment lengths — every one passes the case check and must die on
# the loop at proxy/keycloak-boot-identity.sh:40-45. The id prefix `len-` is the mutation
# selector: `-k "len-"` runs exactly these six against the qa4-5 patched image.
LENGTH_SHAPES = {
    "head-7": "1234567-1234-1234-1234-123456789012",
    "tail-13": "12345678-1234-1234-1234-1234567890123",
    "tail-11": "12345678-1234-1234-1234-12345678901",
    "extra-segment": "12345678-1234-1234-1234-123456789012-1234",
    "short-segment": "12345678-1234-123-1234-123456789012",
    "double-uuid": "12345678-1234-1234-1234-123456789012-87654321-4321-4321-4321-210987654321",
}
# Wrong alphabet (refused by the case check, which qa4-5 does not touch): the hardware
# address of the withdrawn 2026-11-06 primitive, an uppercase UUID, a suffix that must never
# be evaluated by any consumer, and a two-line file whose embedded newline must survive
# `$(cat ...)` as a refusal reason rather than read as one clean token.
ALPHABET_SHAPES = {
    "mac": "02:42:ac:12:00:03",
    "uppercase": "A1B2C3D4-1234-1234-1234-123456789012",
    "injection-suffix": "12345678-1234-1234-1234-123456789012; echo eko-k04-injected",
    "two-line": "12345678-1234-1234-1234-123456789012\ndeadbeef-1234-1234-1234-123456789012\n",
}
ALL_SHAPES = {
    **{f"len-{name}": value for name, value in LENGTH_SHAPES.items()},
    **{f"alpha-{name}": value for name, value in ALPHABET_SHAPES.items()},
}


def write_boot_token(composition: Composition, content: str) -> None:
    """Replace the live token on the carrier volume the way the real rotation writes it.

    A one-off `docker run` of the Keycloak image the composition itself built (uid 1000, the
    rotation's own user) mounts `<project>_keycloak-boot` rw; the host cannot write a
    uid-1000 volume file directly and the proxy's own mount is read-only by design. The
    content arrives on the one-off's stdin (`-i` is load-bearing: without it the container's
    stdin closes immediately, `cat` truncates the file and exits 0 on an EMPTY write — the
    first live run proved that degenerate state by having every refusal arrive as the
    `-s` "no boot token" branch, not as validation), never inside its command line, so the
    injection suffix shape is stored as data and nothing is evaluated. /mnt is the same
    volume the proxy helper reads at /etc/eko/keycloak-boot:ro — only the mount path
    differs. The read-back through the proxy's own mount makes the write observable: a
    shape that never reached the file must fail HERE, not later as an uninformative
    missing-file refusal."""
    image = composition.inspect("keycloak")["Config"]["Image"]
    result = subprocess.run(
        [
            "docker",
            "run",
            "-i",
            "--rm",
            "-v",
            f"{composition.project}_keycloak-boot:/mnt",
            "--entrypoint",
            "sh",
            image,
            "-c",
            "cat > /mnt/token",
        ],
        input=content,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, (
        f"the one-off token write failed ({result.returncode}): {result.stderr[-500:]}"
    )
    read_back = composition.compose(
        "exec", "-T", "proxy", "cat", "/etc/eko/keycloak-boot/token", check=False
    ).stdout
    assert read_back == content, (
        f"the token file holds {read_back!r}, not the written shape {content!r}: the write "
        "degraded, and any refusal from here on would prove the missing-file branch, not "
        "the validation under test"
    )


@pytest.fixture(scope="module")
def open_composition(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Composition]:
    """A fresh composition (the `fresh` teardown discipline) brought to the full open state
    by the real bootstrap, shared by every shape in this file. Module scope is forced by the
    time budget — one bring-up, one proxy restart per shape — and still gives each `-k`
    subset its own bring-up, so a mutation run never consumes an open state an earlier
    un-mutated run left behind."""
    composition = new_composition(tmp_path_factory, "k04")
    try:
        prepare(composition)
        run_bootstrap(composition)
        yield composition
    finally:
        composition.down()


@pytest.fixture(scope="module")
def live_boot(open_composition: Composition) -> str:
    """The boot token the bootstrap actually recorded, pinned before any shape test touches
    the volume: the markers name it, and every refusal below must leave it undisturbed."""
    identity = boot_identity(open_composition)
    assert BOOT_IDENTITY.fullmatch(identity), (
        f"no valid live boot token after the bootstrap: {identity!r}"
    )
    for gate in MARKER_GATES:
        assert marker_value(open_composition, gate) == identity, (
            f"the open state this carrier contrasts against was not established: "
            f"/data/{gate}-open does not name the live boot"
        )
    return identity


@pytest.mark.parametrize("shape", list(ALL_SHAPES.values()), ids=list(ALL_SHAPES.keys()))
def test_k04_malformed_boot_token_refuses_the_identity_path_and_closes_both_listeners(
    open_composition: Composition, live_boot: str, shape: str
) -> None:
    composition = open_composition
    write_boot_token(composition, shape)
    composition.compose("restart", "proxy")
    wait_for_proxy_running(composition)
    # Bind whatever configuration the entrypoint selected before asserting on the sockets:
    # during the restart window nothing listens and a refused connection would fake the
    # closed gate (the EKO-1-12/qa2-3 lesson, inherited by every listener-death claim here).
    time.sleep(3.0)

    refusal = composition.compose("exec", "-T", "proxy", "sh", IDENTITY_SCRIPT, check=False)
    assert refusal.returncode != 0, (
        f"the boot-identity helper ACCEPTED shape {shape!r}: exit {refusal.returncode}, "
        f"stdout {refusal.stdout!r} — the 8-4-4-4-12 segment loop is the only guard between "
        "a written file and an identity the gate callers compare"
    )
    assert refusal.stdout == "", f"the refusing helper printed to stdout: {refusal.stdout!r}"
    # The refusal must come from the VALIDATION branch, not the missing-file one: the
    # read-back in write_boot_token already proved the shape is in the file, so an `-s`
    # message here would mean the composition read a state the test never wrote.
    assert "malformed boot token" in refusal.stderr, (
        f"the refusal did not name the validation branch: stderr tail {refusal.stderr[-200:]!r}"
    )
    assert shape.strip() not in refusal.stderr, "the refused value reached stderr"

    assert_connection_death(composition, "admin")
    assert_connection_death(composition, "auth")
    assert marker_value(composition, "admin") == live_boot, (
        "the closed listeners came from disturbed marker state, not the refused observation"
    )
    assert marker_value(composition, "public") == live_boot


def test_k04_control_a_valid_token_reopens_serving(open_composition: Composition) -> None:
    # listener_open alone would not bind this claim: Keycloak never re-rotated, so nothing
    # but the token FILE changed — the helper must print exactly what was written and the
    # entrypoint must select the open configuration because both markers name it.
    composition = open_composition
    control = str(uuid.uuid4())
    write_boot_token(composition, control)
    for gate in MARKER_GATES:
        write_gate_marker(composition, gate, control)
    composition.compose("restart", "proxy")
    # Settle the restart before reading: `compose exec` fails while the container is still
    # transitioning, and the stdout-stripping `boot_identity` helper would render that race
    # as an empty read — indistinguishable from a refusal (the first live run failed exactly
    # here because the exec was attempted immediately after the restart returned). The two
    # asserts below separate exec failure from helper refusal.
    wait_for_proxy_running(composition)
    reading = composition.compose("exec", "-T", "proxy", "sh", IDENTITY_SCRIPT, check=False)
    assert reading.returncode == 0, (
        "the helper refused the valid token written through the real volume path: "
        f"exit {reading.returncode}, stderr tail {reading.stderr[-200:]!r}"
    )
    assert reading.stdout.strip() == control, (
        f"the helper printed {reading.stdout!r} instead of the written boot identity"
    )
    admin_status = wait_for_serving(composition, "admin")
    assert admin_status == 200, f"admin listener answered {admin_status} on matching markers"
    auth_status = wait_for_serving(composition, "auth")
    assert auth_status == 200, f"auth listener answered {auth_status} on matching markers"
