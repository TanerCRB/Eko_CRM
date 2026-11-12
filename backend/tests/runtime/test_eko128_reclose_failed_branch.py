"""EKO-1-28: committed regression guard for open_gate's re-close-failure branch.

The re-close arm of `open_gate`'s verification-failure tail (`scripts/keycloak-bootstrap.sh`:
the restart after a failed gate has removed its marker) records
"… proxy re-close failed; listeners not confirmed closed" and ends the run at exit 1 when
that restart itself fails. EKO-1-12 proved the arm only under a QA restart stub (exception
EKO-1-12/R-32): deleting its `record` call or its `return 1` turned no committed assertion
red. This file drives the branch through the task's test-only hook,
`EKO128_FORCE_RECLOSE_FAIL`: a non-empty value reports the re-close restart as failed without
any composition fault, consulted ONLY at the re-close point, after the marker removal — unset
or empty behaves exactly as the shipped path (house `${VAR:-}` pattern). The scenario is the
r21 public-gate break (replace only the public site's upstream inside the running proxy, run
the full bootstrap): the gate's own wget verification really times out, the failure tail
really runs, and only the re-close outcome is forced.

The four phases, each on its own `fresh` composition:

- Hook SET on the failing scenario: exit 1 (`run_bootstrap expected=1`), exactly one record
  line contains "verification failed" and that line names "marker removed" and the re-close
  clause, the failed gate's marker is absent (the removal ran before the forced re-close),
  and no "public listener open" record exists (K-01).
- Hook UNSET on the same scenario: the single failure record names "marker removed" and
  "admin listener remains open" and does NOT name the re-close clause — the success-path tail
  shipped today (K-01 contrast, K-02(i)).
- Hook set to the EMPTY STRING: the same success-path tail; activation and "" behave alike
  (K-02(i), the `${VAR:-}` edge).
- Hook SET on a healthy composition: the failure tail never runs, so the hook never fires —
  exit 0, both "listener open" records, both markers naming the live boot identity, no
  "verification failed" line anywhere (K-03: the hook is not a general "fail every restart"
  switch; widening its reach to the first restart dies under this phase, where the bootstrap
  would exit non-zero).

Mutations that must kill the guard (Issue #119): deleting the re-close branch's `record` call
kills the record assertion in the hook-set phase; deleting its `return 1` kills the expected
exit 1; flipping the hook's unset default to always-fail kills the unset and empty-string
phases — and, independently, the two pre-existing guards
`test_eko112_qa_fail_closed_proxy_gate.py::test_qa_open_gate_verification_stops_the_bootstrap_before_the_next_gate`
and `test_eko112_r21_public_gate_residual_state.py` (whose untouched "proxy re-close failed
not in" assertion is exactly what the hook-set phase must NOT collide with: the two tests run
the same scenario on the opposite hook state). What this file does not claim: the wire state
after a forced re-close (the record deliberately refuses to confirm it — only marker absence
and the records are read), and any production protection against the knob being set (none
exists; documenting it test-only is the point of this docstring).
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

pytestmark = pytest.mark.runtime

RECLOSE_FAIL_HOOK = "EKO128_FORCE_RECLOSE_FAIL"
RECLOSE_CLAUSE = "proxy re-close failed; listeners not confirmed closed"
BROKEN_UPSTREAM = "eko128-reclose-unresolvable"


def _break_public_upstream(composition: Composition) -> None:
    """The r21 technique, reused verbatim in effect: break only the PUBLIC site's upstream in
    the running proxy container. The closed and admin-only configurations the entrypoint
    selects while the public marker is absent never load this file, so the admin gate's own
    path stays exactly as in a green bootstrap; the public gate then fails its real 420 s
    verification and reaches the failure tail through the shipped mechanism."""
    broken = composition.compose(
        "exec", "-T", "-u", "0", "proxy", "sh", "-c",
        f"sed -i 's|reverse_proxy @public keycloak:8080|"
        f"reverse_proxy @public {BROKEN_UPSTREAM}:8080|' /etc/caddy/Caddyfile"
        " && grep -c 'reverse_proxy @public' /etc/caddy/Caddyfile",
    )  # fmt: skip
    assert broken.stdout.strip() == "1", (
        f"the public-site break did not apply to /etc/caddy/Caddyfile: {broken.stdout!r}"
    )


def _run_public_gate_failure(
    composition: Composition, evidence: Path, overrides: dict[str, str]
) -> list[str]:
    """The shared scenario spine: break, bootstrap (must exit 1 at the public gate), return
    the recorded events. The exit code is asserted through run_bootstrap's expected=1."""
    result = run_bootstrap(composition, evidence, overrides=overrides, expected=1)
    assert "public listener did not become reachable" in result.stderr, (
        "the run did not fail at the public gate's own verification; the failure tail was "
        f"not reached through the real mechanism:\n{result.stderr[-2000:]}"
    )
    events = [
        line
        for line in evidence.read_text(encoding="utf-8").splitlines()
        if line
    ]
    # The scenario preconditions every clause depends on: the provider check ran, the admin
    # gate opened (so the public failure tail runs against the live admin marker), and the
    # public gate's success record is impossible.
    assert any("custom provider selected" in line for line in events), (
        "the pre-listener provider verification did not run: the scenario is broken"
    )
    assert any("admin listener open" in line for line in events), (
        "the admin gate did not open in this scenario; the residual-state clause tests nothing"
    )
    assert not any("public listener open" in line for line in events), (
        "the bootstrap recorded the public gate open although its own verification failed"
    )
    # K-01 "Nothing" edge: one failure record line per run, for the failing gate.
    failure_lines = [line for line in events if "verification failed" in line]
    assert len(failure_lines) == 1, f"expected exactly one failure record line: {events}"
    assert "public verification failed" in failure_lines[0], failure_lines[0]
    # The Order edge: the marker removal ran before the (forced or real) re-close, so the
    # failed gate's marker is gone whatever the re-close reported.
    assert marker_value(composition, "public") == "", (
        "the failed public gate left its marker on the volume"
    )
    return failure_lines


def test_eko128_hook_set_records_the_reclose_failure_and_exits_one(
    fresh: Composition, tmp_path: Path
) -> None:
    """K-01: with the hook active the re-close-failure branch is the one recorded, and the
    run exits 1 — the branch EKO-1-12 could only prove under a QA restart stub."""
    prepare(fresh)
    _break_public_upstream(fresh)
    failure_lines = _run_public_gate_failure(
        fresh,
        tmp_path / "bootstrap-hook-set.jsonl",
        {RECLOSE_FAIL_HOOK: "fail"},
    )
    assert "marker removed" in failure_lines[0], failure_lines[0]
    assert RECLOSE_CLAUSE in failure_lines[0], (
        "the re-close-failure branch did not record its clause: " + failure_lines[0]
    )


def test_eko128_hook_unset_records_the_success_path_tail(
    fresh: Composition, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-01 contrast / K-02(i): with the hook never set by the caller (and no ambient host
    leak), the same scenario records the shipped success-path residual and the real re-close
    restart ran — no re-close clause appears anywhere."""
    monkeypatch.delenv(RECLOSE_FAIL_HOOK, raising=False)
    prepare(fresh)
    _break_public_upstream(fresh)
    failure_lines = _run_public_gate_failure(
        fresh, tmp_path / "bootstrap-hook-unset.jsonl", {}
    )
    assert "marker removed" in failure_lines[0], failure_lines[0]
    assert "admin listener remains open" in failure_lines[0], (
        "the unset hook changed the shipped residual record: " + failure_lines[0]
    )
    assert RECLOSE_CLAUSE not in failure_lines[0], (
        "the unset path took the re-close-failure arm; the knob is consulted or defaulted "
        "when absent: " + failure_lines[0]
    )


def test_eko128_hook_empty_string_behaves_as_unset(
    fresh: Composition, tmp_path: Path
) -> None:
    """K-02(i) "Nothing" edge: a set-but-empty knob is the shipped path, byte-identical to
    the unset phase's records (the house `${VAR:-}` reading)."""
    prepare(fresh)
    _break_public_upstream(fresh)
    failure_lines = _run_public_gate_failure(
        fresh,
        tmp_path / "bootstrap-hook-empty.jsonl",
        {RECLOSE_FAIL_HOOK: ""},
    )
    assert "marker removed" in failure_lines[0], failure_lines[0]
    assert "admin listener remains open" in failure_lines[0], (
        "the empty-string hook changed the shipped residual record: " + failure_lines[0]
    )
    assert RECLOSE_CLAUSE not in failure_lines[0], (
        "the empty-string path took the re-close-failure arm: " + failure_lines[0]
    )


def test_eko128_hook_set_on_a_healthy_bootstrap_completes_open(
    fresh: Composition, tmp_path: Path
) -> None:
    """K-03: the hook reaches only the re-close tail. A healthy composition never enters
    that tail, so the knob is inert: the full bootstrap exits 0 with both gates open and
    both markers naming the live boot — the same end state as a hook-free green run."""
    prepare(fresh)
    evidence = tmp_path / "bootstrap-hook-set-healthy.jsonl"
    run_bootstrap(
        fresh, evidence, overrides={RECLOSE_FAIL_HOOK: "fail"}, expected=0
    )  # fmt: skip
    events = [
        line
        for line in evidence.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert not any("verification failed" in line for line in events), (
        f"a healthy bootstrap with the hook set recorded a failed gate: {events}"
    )
    assert any("admin listener open" in line for line in events), (
        "the admin gate did not open with the hook set: the hook reached the first restart "
        "or an earlier step"
    )
    assert any("public listener open" in line for line in events), (
        "the public gate did not open with the hook set: the hook reached the live path"
    )
    identity = boot_identity(fresh)
    assert identity, "the proxy cannot observe the current Keycloak boot identity"
    assert marker_value(fresh, "admin") == identity, (
        "the admin marker does not name the live boot after a hook-set green run"
    )
    assert marker_value(fresh, "public") == identity, (
        "the public marker does not name the live boot after a hook-set green run"
    )
