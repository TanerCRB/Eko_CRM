"""EKO-1-15 K-02 (ADR-0004-C31) and the K-03 partial-push edge, added by QA:
`scripts/release-images.sh`, the one place the release run turns checked images into pushed
digests, run against a stand-in `docker` on PATH (no daemon, no registry).

The stand-in answers `image inspect` with the image ID the environment gives
(STUB_ID_<NAME>) or with a repository digest (STUB_DIGEST_<NAME>, a value distinct from every
ID), logs every call, and fails the push named by STUB_FAIL_PUSH.
"""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tests.support.repo import REPO_ROOT, bash

SCRIPT = REPO_ROOT / "scripts" / "release-images.sh"
# EKO-1-26 route A: the custom Keycloak image is the fifth project image — checked, pushed and
# digested like the four before it; postgres stays the only image digested from a runtime pull.
NAMES = ("backend", "frontend", "proxy", "backup", "keycloak")
REGISTRY = "ghcr.io/tanercrb/eko-crm"
TAG = "v1.2.0"
# The stand-in directory first on PATH; Git Bash on Windows needs it as /c/..., not C:/...
WITH_STAND_IN = (
    'PATH="$(cygpath -u "$EKO_QA_STAND_IN" 2>/dev/null || printf %s "$EKO_QA_STAND_IN")'
    ':$PATH"; exec bash "$0" "$@"'
)

STAND_IN = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_LOG"
upper() { printf '%s' "$1" | tr '[:lower:]' '[:upper:]'; }
if [ "$1" = image ] && [ "$2" = inspect ]; then
  format="$4"; ref="$5"
  if [[ "$format" == *RepoDigests* ]]; then
    repo="${ref%:*}"; name="${repo##*/}"; var="STUB_DIGEST_$(upper "$name")"
    printf '%s@%s\\n' "$repo" "${!var}"
  else
    name="${ref#eko-crm/}"; name="${name%%:*}"; var="STUB_ID_$(upper "$name")"
    printf '%s\\n' "${!var:-}"
  fi
  exit 0
fi
if [ "$1" = push ]; then
  ref="${*: -1}"; name="${ref##*/}"; name="${name%%:*}"
  [ "${STUB_FAIL_PUSH:-}" = "$name" ] && exit 1
fi
exit 0
"""


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


IDS = {name: sha(f"id-{name}") for name in NAMES}
DIGESTS = {name: sha(f"registry-{name}") for name in NAMES}


def run(
    tmp_path: Path, *args: str, ids: dict[str, str] = IDS, fail_push: str = ""
) -> tuple[int, str, list[str]]:
    stand_in = tmp_path / "bin"
    stand_in.mkdir(exist_ok=True)
    docker = stand_in / "docker"
    docker.write_text(STAND_IN, encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8")
    env = {**os.environ, "STUB_LOG": log.as_posix(), "STUB_FAIL_PUSH": fail_push}
    env["EKO_QA_STAND_IN"] = stand_in.as_posix()
    for name in NAMES:
        env[f"{name.upper()}_ID"] = IDS[name]
        env[f"STUB_ID_{name.upper()}"] = ids[name]
        env[f"STUB_DIGEST_{name.upper()}"] = DIGESTS[name]
    # The pulled third party (EKO-1-26: postgres alone — keycloak's digest comes from the push).
    env["STUB_DIGEST_POSTGRES"] = sha("registry-postgres")
    result = subprocess.run(
        [bash(), "-c", WITH_STAND_IN, SCRIPT.as_posix(), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    calls = log.read_text(encoding="utf-8").splitlines()
    return result.returncode, result.stdout, calls


def test_eko115_k02_qa_identity_check_passes_the_checked_images(tmp_path: Path) -> None:
    code, _, calls = run(tmp_path, "check-identity")
    assert code == 0
    assert len([c for c in calls if c.startswith("image inspect")]) == len(NAMES)


def test_eko115_k02_qa_contrast_identity_check_fails_on_another_image(tmp_path: Path) -> None:
    rebuilt = {**IDS, "frontend": sha("id-frontend-rebuilt")}
    code, _, _ = run(tmp_path, "check-identity", ids=rebuilt)
    assert code == 1


def test_eko115_k02_qa_push_prints_the_registry_digests_of_the_checked_images(
    tmp_path: Path,
) -> None:
    code, out, calls = run(tmp_path, "push", TAG)
    assert code == 0
    assert out.splitlines() == [f"{name}={DIGESTS[name]}" for name in NAMES]
    for name in NAMES:
        assert f"tag eko-crm/{name}:checked {REGISTRY}/{name}:{TAG}" in calls, calls
    assert [c for c in calls if "build" in c] == []


def test_eko115_k02_qa_push_of_a_rebuilt_image_pushes_nothing(tmp_path: Path) -> None:
    rebuilt = {**IDS, "proxy": sha("id-proxy-rebuilt")}
    code, out, calls = run(tmp_path, "push", TAG, ids=rebuilt)
    assert code == 1 and out == ""
    assert [c for c in calls if c.startswith("push") or c.startswith("tag")] == []


@pytest.mark.parametrize("failing", ["proxy"])
def test_eko115_k03_qa_failed_third_push_ends_the_step_without_all_digests(
    tmp_path: Path, failing: str
) -> None:
    # The step writes this output to digests.env; the render after it never runs (K-03 edge).
    code, out, _ = run(tmp_path, "push", TAG, fail_push=failing)
    assert code != 0
    assert [line.split("=")[0] for line in out.splitlines()] == ["backend", "frontend"]


def test_eko126_k03_qa_keycloak_is_a_pushed_image_not_a_pulled_one(tmp_path: Path) -> None:
    """EKO-1-26 K-03: the release demands no registry digest for what it does not publish. The
    custom keycloak image is now pushed (`push` prints its registry digest, in the five-image
    order), so `pulled-digests` — the runtime tests' pulled references — names postgres only."""
    pushed_code, pushed_out, _ = run(tmp_path, "push", TAG)
    assert pushed_code == 0 and "keycloak" in pushed_out.splitlines()[-1], pushed_out
    pulled_code, pulled_out, pulled_calls = run(tmp_path, "pulled-digests")
    assert pulled_code == 0, pulled_out
    assert pulled_out.splitlines() == [f"postgres={sha('registry-postgres')}"], pulled_out
    # No keycloak reference is inspected as a pull: it is not a compose third-party digest source.
    assert [c for c in pulled_calls if "keycloak" in c] == [], pulled_calls
