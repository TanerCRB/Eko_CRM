"""EKO-1-12 reviewer re-review round 2 (R-21): the failed PUBLIC gate's residual record
names the state that actually survives, and a failed re-close restart is not swallowed.

The shared failure tail of `open_gate` used to record "listeners closed" for whichever gate
failed. That is true only for the admin gate, the first marker written (contrast 3 in
test_eko112_qa_fail_closed_proxy_gate.py). When the PUBLIC gate fails, the admin marker still
names the live Keycloak boot, so the re-close restart leaves the proxy serving the admin
listener — the record claimed a closed state while 8443 kept answering, the same
evidence-versus-wire disagreement R-06 was fixed for, reintroduced on the other gate. The
tail also ran `compose restart proxy >/dev/null || true`: a failed re-close (marker gone, old
configuration still loaded) passed silently while the record asserted closure.

The scenario executed here mirrors contrast 3's technique on the other site: the full
Caddyfile's public upstream is replaced with an unresolvable name inside the proxy container
before the bootstrap runs. The admin gate opens normally (its site is untouched); when the
public marker selects the full configuration, the public listener never serves the discovery
document, the gate's own wget verification times out at its 420 s ceiling, and the failure
path must: exit non-zero, remove only the public marker, re-close onto Caddyfile.admin —
leaving the admin listener live — and record that surviving state truthfully. Removing the
gate-specific residual branch from `open_gate` (the shared "listeners closed" wording) kills
the record assertion; removing the `if` guard around the re-close restart (a swallowed
`|| true`) is the failure direction the record's "proxy re-close failed" branch exists for.
"""

from pathlib import Path

import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    boot_identity,
    marker_value,
    prepare,
    run_bootstrap,
)
from tests.runtime.test_eko112_qa_fail_closed_proxy_gate import (
    assert_connection_death,
    wait_for_serving,
)

pytestmark = pytest.mark.runtime

BROKEN_UPSTREAM = "eko112-r21-unresolvable"


def test_r21_failed_public_gate_records_the_surviving_admin_open_state(
    fresh: Composition, tmp_path: Path
) -> None:
    prepare(fresh)
    assert_connection_death(fresh, "admin")
    assert_connection_death(fresh, "auth")

    # Break only the PUBLIC site's upstream, in the running container: the closed and
    # admin-only configurations Caddy selects while the public marker is absent never
    # load this file, so the admin gate's own path stays exactly as in a green bootstrap.
    broken = fresh.compose(
        "exec", "-T", "-u", "0", "proxy", "sh", "-c",
        f"sed -i 's|reverse_proxy @public keycloak:8080|"
        f"reverse_proxy @public {BROKEN_UPSTREAM}:8080|' /etc/caddy/Caddyfile"
        " && grep -c 'reverse_proxy @public' /etc/caddy/Caddyfile",
    )  # fmt: skip
    assert broken.stdout.strip() == "1", (
        f"the public-site break did not apply to /etc/caddy/Caddyfile: {broken.stdout!r}"
    )

    # The bootstrap runs the real scenario: admin gate opens, application mode completes,
    # then the public gate's verification never succeeds and the whole run exits non-zero.
    # The 420 s reachability ceiling is the mechanism's own deadline; this is the run's cost.
    evidence = tmp_path / "bootstrap-public-failure.jsonl"
    result = run_bootstrap(fresh, evidence, expected=1)
    assert "public listener did not become reachable" in result.stderr, (
        f"the bootstrap did not fail at the public gate verification:\n{result.stderr[-2000:]}"
    )

    events = [line for line in evidence.read_text(encoding="utf-8").splitlines() if line]
    assert any("custom provider selected" in line for line in events), (
        "the pre-listener provider verification did not run: the contrast scenario is broken"
    )
    assert any("admin listener open" in line for line in events), (
        "the admin gate did not open in this scenario; nothing tested the residual claim"
    )
    assert not any("public listener open" in line for line in events), (
        "the bootstrap recorded the public gate open although its own verification failed"
    )

    # The record assertion: the failure line names the SURVIVING state, and the shared
    # "listeners closed" claim is gone (it was false here — the admin marker still serves).
    failure_lines = [line for line in events if "verification failed" in line]
    assert len(failure_lines) == 1, f"expected exactly one failure record line: {events}"
    assert "public verification failed" in failure_lines[0], failure_lines[0]
    assert "marker removed" in failure_lines[0], failure_lines[0]
    assert "admin listener remains open" in failure_lines[0], (
        f"the residual record does not name the surviving admin-open state: {failure_lines[0]}"
    )
    assert "proxy re-close failed" not in failure_lines[0], (
        "the re-close restart failed in this scenario; the surviving-state claim below "
        "cannot be attributed to the re-close branch: " + failure_lines[0]
    )
    assert not any("listeners closed" in line for line in events), (
        f"a record line still claims both listeners closed: {events}"
    )

    # The wire agrees with the record: only the failed gate's marker is gone, the admin
    # marker still names the live boot, and the proxy re-selected the admin-only file.
    assert marker_value(fresh, "public") == "", "the failed public gate left its marker"
    identity = boot_identity(fresh)
    assert identity, "the proxy cannot observe the current Keycloak boot identity"
    assert marker_value(fresh, "admin") == identity, (
        "the admin marker no longer names the live boot: the surviving-state assertion "
        "below would be testing a stale gate, not the recorded residual"
    )
    status = wait_for_serving(fresh, "admin")
    assert status == 200, f"admin listener answered {status} — the record claims it survives"
    assert_connection_death(fresh, "auth")
