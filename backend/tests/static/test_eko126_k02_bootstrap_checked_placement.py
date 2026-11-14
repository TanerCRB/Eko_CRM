"""EKO-1-26 fix round 1 (QA F-1, F-2): the bootstrap composes the placement the session proves.

`scripts/keycloak-bootstrap.sh` starts Keycloak through Compose. Under EKO_CHECKED_IMAGES it must
start the PLACED checked image: without the override the release-mode session runs the development
anchor (fresh CI runner: the script's `up keycloak` builds in session and the K-04 guard must flag
it — run 42954811816's shape; host with a pre-existing anchor: an image `check-identity` never
verified). The override the script passes is the same placement semantics the runtime harness
applies (`checked_images_override` in backend/tests/runtime/conftest.py — checked `image:`,
`build: !reset null`, `pull_policy: never`, backup-manifest mirror); a test below compares the
rendered files byte for byte so the script cannot grow a second, drifting semantics. With the
variable unset the keycloak starts keep exactly the file arguments the development path has always
used: base compose file (anchor + `build: ./identity` kept, K-05), plus the bootstrap's own
KC_BOOTSTRAP override on the first start only.

The script runs against a recording `docker` double on PATH — no daemon, no container, no volume:
the double logs every invocation, copies every `-f` file it is handed, and answers the canned
outputs (fake container ids, the provider-selection log line, a synthetic boot identity) so the
bootstrap walks its whole ordered flow offline. The composition files the assertions read are the
artifacts the script itself generated, rendered with the real Compose CLI — the shape of the
harness freeze carriers. F-2 lives here too: the session-images guard's Compose-name fallback must
name the fifth family member, never only the first four.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.runtime import conftest as harness
from tests.support import session_images as si
from tests.support.repo import REPO_ROOT, bash, render

CHECKED = {
    name: f"eko-crm/{name}:checked"
    for name in ("backend", "frontend", "proxy", "backup", "keycloak")
}
# the exact five-pair literal the release-mode job exports (.github/workflows/ci.yml)
GIVEN = " ".join(f"{name}={CHECKED[name]}" for name in CHECKED)
INCOMPLETE = " ".join(f"{name}={CHECKED[name]}" for name in CHECKED if name != "keycloak")
KEYCLOAK_ANCHOR = "localhost/eko-crm/keycloak:26.8.1-eko112"

SHIM = r"""#!/usr/bin/env bash
# recording docker double: logs the call, copies every -f file it is handed into the snapshot
# directory, answers the canned outputs that let the bootstrap finish offline. Never a daemon.
printf '%s\n' "$*" >> "$EKO112_FAKE_LOG"
FACTORY_PART1="KC-SERVICES0047: jpa (org.eko_crm.keycloak.events."
FACTORY_PART2="FilteringJpaEventStoreProviderFactory) is active"
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
  *test\ -f\ /data/master-initialized)
    [ "${EKO112_FAKE_RERUN:-false}" = true ] || exit 1 ;;
  *python\ /tmp/eko112-bootstrap.py*)
    printf '{"event":"master accounts ready"}\n' ;;
  *ps\ -q\ backend) printf 'fake-backend-container\n' ;;
  *ps\ -q\ keycloak) printf 'fake-keycloak-container\n' ;;
  *logs\ keycloak*) printf '%s\n' "$FACTORY_PART1$FACTORY_PART2" ;;
  *eko-keycloak-boot-identity.sh*) printf '123e4567-e89b-12d3-a456-426614174000\n' ;;
esac
exit 0
"""


def posix(path: Path) -> str:
    """A Git-Bash-visible form of a Windows path (the double and the wrapper are bash)."""
    forward = str(path).replace("\\", "/")
    return re.sub(r"^([A-Za-z]):/", lambda m: f"/{m.group(1).lower()}/", forward)


def run_bootstrap(
    tmp_path: Path, synthetic_env: Path, *, checked: str | None, rerun: bool
) -> dict[str, Any]:
    """The bootstrap, offline, against the recording double; its artifacts come back as a dict."""
    home = tmp_path / "bootstrap"
    home.mkdir()
    env_file = home / "bootstrap.env"
    env_file.write_text(synthetic_env.read_text(encoding="utf-8"), encoding="utf-8")
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "docker"
    shim.write_text(SHIM, encoding="utf-8", newline="\n")
    snap = tmp_path / "snap"
    snap.mkdir()
    log = tmp_path / "calls.txt"
    subprocess.run([bash(), "-c", 'chmod +x "$1"', "carrier", posix(shim)], check=True)
    child_env = dict(os.environ)
    for name in ("COMPOSE_FILE", "COMPOSE_PROFILES", "EKO_CHECKED_IMAGES"):
        child_env.pop(name, None)
    if checked is not None:
        child_env["EKO_CHECKED_IMAGES"] = checked
    child_env["EKO112_FAKE_LOG"] = posix(log)
    child_env["EKO112_FAKE_SNAP"] = posix(snap)
    child_env["EKO112_FAKE_RERUN"] = "true" if rerun else "false"
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
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return {
        "rc": result.returncode,
        "out": result.stdout + result.stderr,
        "calls": calls,
        "snap": snap,
        "env_file": env_file,
    }


def keycloak_up_lines(calls: list[str]) -> list[str]:
    return [
        line for line in calls if " up -d --force-recreate " in line and line.endswith(" keycloak")
    ]


def passed_files(line: str) -> list[str]:
    """The values of every `-f` that precedes the `up` subcommand of this recorded call."""
    tokens = line.split()
    up = tokens.index("up")
    return [tokens[index + 1] for index, token in enumerate(tokens[:up]) if token == "-f"]


def test_eko126_k02_release_mode_bootstrap_starts_carry_the_checked_placement(
    tmp_path: Path, synthetic_env: Path
) -> None:
    """F-1: with EKO_CHECKED_IMAGES set, every keycloak start of the bootstrap composes through
    the placement override, and the override freezes keycloak exactly where the harness freeze
    carriers freeze it: the placed image, no build, never a pull, manifest mirror included.
    The override's directory must not outlive the run (hygiene)."""
    run = run_bootstrap(tmp_path, synthetic_env, checked=GIVEN, rerun=False)
    assert run["rc"] == 0, run["out"]
    lines = keycloak_up_lines(run["calls"])
    assert len(lines) == 2, run["calls"]
    bootstrap_files, recreate_files = (passed_files(line) for line in lines)
    assert [Path(f).name for f in bootstrap_files[:2]] == ["compose.yaml", "checked-images.yaml"], (
        bootstrap_files
    )
    assert len(bootstrap_files) == 3 and ".override." in bootstrap_files[2], bootstrap_files
    assert [Path(f).name for f in recreate_files] == [
        "compose.yaml",
        "checked-images.yaml",
    ], recreate_files
    override = run["snap"] / "checked-images.yaml"
    assert override.is_file()
    services = render(run["env_file"], dev_profile=True, extra_files=[override])["services"]
    keycloak = services["keycloak"]
    assert keycloak["image"] == CHECKED["keycloak"]
    assert "build" not in keycloak
    assert keycloak["pull_policy"] == "never"
    manifest = services["backup"]["environment"]
    assert manifest["BACKUP_MANIFEST_KEYCLOAK_IMAGE"] == CHECKED["keycloak"]
    assert manifest["BACKUP_MANIFEST_BACKEND_IMAGE"] == CHECKED["backend"]
    checked_dir = Path(bootstrap_files[1]).parent
    assert not checked_dir.exists(), f"the placement override outlived the bootstrap: {checked_dir}"


def test_eko126_k02_rerun_path_bootstrap_start_carries_the_checked_placement(
    tmp_path: Path, synthetic_env: Path
) -> None:
    """The recreate branch starts keycloak too: under EKO_CHECKED_IMAGES that start carries the
    same two files (base + override) — a fix on the bootstrap-only path would leave this open."""
    run = run_bootstrap(tmp_path, synthetic_env, checked=GIVEN, rerun=True)
    assert run["rc"] == 0, run["out"]
    lines = keycloak_up_lines(run["calls"])
    assert len(lines) == 1, run["calls"]
    assert [Path(f).name for f in passed_files(lines[0])] == [
        "compose.yaml",
        "checked-images.yaml",
    ]


def test_eko126_k02_bootstrap_override_matches_the_harness_byte_for_byte(
    tmp_path: Path, synthetic_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One semantics, not two: the file the script renders for the pairs of the job is the file
    the runtime harness writes for the same value — compared byte for byte."""
    run = run_bootstrap(tmp_path, synthetic_env, checked=GIVEN, rerun=False)
    assert run["rc"] == 0, run["out"]
    monkeypatch.setenv("EKO_CHECKED_IMAGES", GIVEN)
    harness.checked_images_override.cache_clear()
    try:
        harness_override = harness.checked_images_override()
        assert harness_override is not None
        expected = Path(harness_override).read_text(encoding="utf-8")
    finally:
        monkeypatch.delenv("EKO_CHECKED_IMAGES", raising=False)
        harness.checked_images_override.cache_clear()
    written = run["snap"] / "checked-images.yaml"
    assert written.is_file(), run["calls"]
    assert written.read_text(encoding="utf-8") == expected


def test_eko126_k02_contrast_without_the_variable_the_keycloak_starts_stay_the_dev_ones(
    tmp_path: Path, synthetic_env: Path
) -> None:
    """K-05 and the byte-identical development path: with EKO_CHECKED_IMAGES unset the first
    start carries exactly base + the bootstrap's own KC_BOOTSTRAP override (no placement file
    anywhere), the recreate carries no `-f` at all (the default base it always used), and the
    composition rendered from the script's own files keeps the anchor and its
    `build: ./identity`."""
    run = run_bootstrap(tmp_path, synthetic_env, checked=None, rerun=False)
    assert run["rc"] == 0, run["out"]
    lines = keycloak_up_lines(run["calls"])
    assert len(lines) == 2, run["calls"]
    bootstrap_files, recreate_files = (passed_files(line) for line in lines)
    assert Path(bootstrap_files[0]).name == "compose.yaml", bootstrap_files
    assert len(bootstrap_files) == 2 and ".override." in bootstrap_files[1], bootstrap_files
    assert recreate_files == [], recreate_files
    assert not (run["snap"] / "checked-images.yaml").exists()
    bootstrap_overrides = list(run["snap"].glob("bootstrap.env.override.*"))
    assert len(bootstrap_overrides) == 1, list(run["snap"].iterdir())
    services = render(
        run["env_file"],
        dev_profile=True,
        compose_file=REPO_ROOT / "compose.yaml",
        extra_files=[bootstrap_overrides[0]],
    )["services"]
    keycloak = services["keycloak"]
    assert keycloak["image"] == KEYCLOAK_ANCHOR
    assert Path(keycloak["build"]["context"]).resolve() == (REPO_ROOT / "identity")


def test_eko126_k02_contrast_rerun_without_the_variable_starts_with_the_default_base(
    tmp_path: Path, synthetic_env: Path
) -> None:
    run = run_bootstrap(tmp_path, synthetic_env, checked=None, rerun=True)
    assert run["rc"] == 0, run["out"]
    lines = keycloak_up_lines(run["calls"])
    assert len(lines) == 1, run["calls"]
    assert passed_files(lines[0]) == []
    assert not (run["snap"] / "checked-images.yaml").exists()


def test_eko126_k02_an_incomplete_checked_list_refuses_before_any_compose_call(
    tmp_path: Path, synthetic_env: Path
) -> None:
    """Fail closed the way the harness ValueError refuses: the pairs name no keycloak image, so
    the bootstrap refuses it before touching the composition — never a silent dev-anchor start."""
    run = run_bootstrap(tmp_path, synthetic_env, checked=INCOMPLETE, rerun=False)
    assert run["rc"] != 0, run["out"]
    assert "names no image for keycloak" in run["out"], run["out"]
    assert run["calls"] == []


def test_eko126_k02_a_whitespace_only_checked_list_refuses_rather_than_silently_dev(
    tmp_path: Path, synthetic_env: Path
) -> None:
    """A set-but-vacuous EKO_CHECKED_IMAGES cannot name the placement, and the harness renders no
    override for it (None). The script chooses the fail-closed side of that gap: refusing beats
    silently running the development anchor under a variable the caller clearly meant as a
    release signal. This test pins that direction (assumption A-02); nothing on the CI path
    exports a vacuous list, so it never fires there."""
    run = run_bootstrap(tmp_path, synthetic_env, checked="   ", rerun=False)
    assert run["rc"] != 0, run["out"]
    assert "names no image for" in run["out"], run["out"]
    assert run["calls"] == []


def test_eko126_k01_the_compose_name_fallback_covers_the_fifth_family_member() -> None:
    """F-2: a session-built image named `<project>-keycloak` without the compose label must be
    caught by the COMPOSE_NAME fallback — the list of guardable service names gains keycloak."""
    placed: dict[str, dict[str, str]] = {image: {} for image in CHECKED.values()}
    built = "ekort-fresh-0badc0de-keycloak:latest"
    found = si.violations(set(placed), {**placed, built: {}})
    assert found == [f"{built}: named as Compose names a project's built image"], found
