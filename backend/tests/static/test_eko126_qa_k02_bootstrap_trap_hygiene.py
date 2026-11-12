"""EKO-1-26 QA (fix round 1): the failed-closed half of the placement hygiene claim.

The success-path carriers read the placement directory away only after a run that completed —
the ERR traps' cleanup is invisible to them, and QA mutation EKO-1-26-M10b (file-top trap
cleanup removed, final cleanup kept) survived every committed check at e3250fc. This carrier
drives the real script to failures in the two windows whose traps carry the cleanup today: the
pre-start marker removal (the file-top ERR trap) and the first keycloak start (the
bootstrap-override trap text). A third window — a failure at the second keycloak start, after
the RERUN=false block restores the bare ERR-trap text — LEAKS the directory at this head, as do
the explicit `exit 1`/`exit 6` paths (the ERR trap never fires on an explicit exit); that gap is
finding EKO-1-26/F-3 for the developer, not an assertion here (an assertion of it would be red
and this suite must stay green at the checkpoint).
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.static.test_eko126_k02_bootstrap_checked_placement import GIVEN, posix
from tests.support.repo import REPO_ROOT, bash

# The recording double of the placement carriers plus two failure hooks. Windows: "markers"
# fails the pre-start marker removal (under the file-top ERR trap), "up1" the first keycloak
# start (under the bootstrap-override trap). Both traps clean the placement directory today.
FAILING_SHIM = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$EKO112_FAKE_LOG"
if [ "${1:-}" = "compose" ]; then
  shift
  prev=""
  for a in "$@"; do
    if [ "$prev" = "-f" ] && [ -r "$a" ]; then
      mkdir -p "$EKO112_FAKE_SNAP"
      cp -- "$a" "$EKO112_FAKE_SNAP/$(basename -- "$a")"
    fi
    prev="$a"
  done
fi
case "$*" in
  *exec\ -T\ proxy\ rm\ -f\ /data/admin-open*)
    [ "${EKO112_FAKE_FAIL_MARKERS:-false}" = true ] && exit 1 ;;
  *test\ -f\ /data/master-initialized)
    [ "${EKO112_FAKE_RERUN:-false}" = true ] || exit 1 ;;
  *python\ /tmp/eko112-bootstrap.py*)
    printf '{"event":"master accounts ready"}\n' ;;
  *ps\ -q\ backend) printf 'fake-backend-container\n' ;;
  *ps\ -q\ keycloak) printf 'fake-keycloak-container\n' ;;
  *up\ -d\ --force-recreate\ --wait*)
    if printf '%s' "$*" | grep -q '\.override\.'; then
      [ "${EKO112_FAKE_FAIL_UP1:-false}" = true ] && exit 1
    fi ;;
  *logs\ keycloak*)
    printf '%s\n' 'KC-SERVICES0047: jpa (org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory) is active' ;;
  *eko-keycloak-boot-identity.sh*) printf '123e4567-e89b-12d3-a456-426614174000\n' ;;
esac
exit 0
"""

WINDOW_HOOKS = {
    "markers": {"EKO112_FAKE_FAIL_MARKERS": "true"},
    "up1": {"EKO112_FAKE_FAIL_UP1": "true"},
}


def _run_failing_bootstrap(tmp_path: Path, synthetic_env: Path, window: str) -> dict:
    home = tmp_path / "bootstrap"
    home.mkdir()
    env_file = home / "bootstrap.env"
    env_file.write_text(synthetic_env.read_text(encoding="utf-8"), encoding="utf-8")
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "docker"
    shim.write_text(FAILING_SHIM, encoding="utf-8", newline="\n")
    snap = tmp_path / "snap"
    snap.mkdir()
    log = tmp_path / "calls.txt"
    subprocess.run([bash(), "-c", 'chmod +x "$1"', "carrier", posix(shim)], check=True)
    child_env = dict(os.environ)
    for name in ("COMPOSE_FILE", "COMPOSE_PROFILES"):
        child_env.pop(name, None)
    child_env["EKO_CHECKED_IMAGES"] = GIVEN
    child_env["EKO112_FAKE_LOG"] = posix(log)
    child_env["EKO112_FAKE_SNAP"] = posix(snap)
    child_env.update(WINDOW_HOOKS[window])
    result = subprocess.run(
        [
            bash(),
            "-c",
            'PATH="$1:$PATH"; exec bash "$2" "$3"',
            "carrier",
            posix(shim_dir),
            posix(REPO_ROOT / "scripts" / "keycloak-bootstrap.sh"),
            posix(env_file),
        ],
        cwd=REPO_ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    return {
        "rc": result.returncode,
        "out": result.stdout + result.stderr,
        "calls": log.read_text(encoding="utf-8").splitlines() if log.exists() else [],
    }


@pytest.mark.parametrize("window", sorted(WINDOW_HOOKS))
def test_eko126_qa_k02_a_failing_release_run_removes_the_placement_directory(
    tmp_path: Path, synthetic_env: Path, window: str
) -> None:
    """Every ERR trap that guards a placement-carrying window must delete the directory when
    the run fails closed — one semantics, no window left out."""
    run = _run_failing_bootstrap(tmp_path, synthetic_env, window)
    assert run["rc"] != 0, run["out"]
    assert "failed closed" in run["out"], run["out"]
    placements = [
        token
        for line in run["calls"]
        for token in line.split()
        if token.endswith("checked-images.yaml")
    ]
    # both windows are reached only after the placement has been rendered and passed to a
    # compose call (the RERUN probe carries it in the markers window), so the directory the
    # trap must delete is always identifiable from the recorded arguments
    assert placements, run["calls"]
    checked_dir = Path(placements[0]).parent
    assert not checked_dir.exists(), f"the placement override outlived the failed run: {checked_dir}"
