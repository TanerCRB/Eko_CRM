"""EKO-1-15 K-07, runtime half: the development profile builds its project images locally and
starts with no credential for the project registry and no cached project image.

The Docker client gets an empty configuration directory (DOCKER_CONFIG), so it holds no
credential for `ghcr.io`; every locally cached `ghcr.io/tanercrb/eko-crm/*` image is removed
first. Public third-party images are still pulled, as today. Contrast: the release composition
under the same condition cannot pull its backend.

Not covered: the daemon's network path to `ghcr.io` is not cut, so "unreachable" is shown only by
the missing credential and by no image of the project registry being named or pulled.
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.runtime.conftest import UP_TIMEOUT_SECONDS, Composition
from tests.support import release_composition as rc
from tests.support.repo import REPO_ROOT, write_synthetic_env

pytestmark = pytest.mark.runtime

PROJECT_REGISTRY = "ghcr.io/tanercrb/eko-crm"


def no_credential(tmp_path: Path) -> dict[str, str]:
    config = tmp_path / "docker-config"
    config.mkdir()
    (config / "config.json").write_text("{}", encoding="utf-8")
    return {**os.environ, "DOCKER_CONFIG": str(config)}


def run(args: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )


def remove_cached_project_images() -> None:
    listed = subprocess.run(
        ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for image in [i for i in listed if i.startswith(PROJECT_REGISTRY)]:
        subprocess.run(["docker", "image", "rm", "-f", image], capture_output=True, check=False)


def test_eko115_k07_development_profile_starts_without_the_project_registry(
    fresh: Composition, tmp_path: Path
) -> None:
    remove_cached_project_images()
    env = no_credential(tmp_path)
    up = run(
        [*fresh.base_args(), "up", "--build", "--wait", "--wait-timeout", str(UP_TIMEOUT_SECONDS)],
        env,
        UP_TIMEOUT_SECONDS + 300,
    )
    assert up.returncode == 0, up.stderr[-4000:]
    images = run([*fresh.base_args(), "images", "--format", "json"], env, 120).stdout
    assert PROJECT_REGISTRY not in images
    # Public build bases (ghcr.io/astral-sh/uv) are pulled as today; the project registry never.
    assert "ghcr.io/tanercrb" not in (up.stdout + up.stderr).lower()


def test_eko115_k07_contrast_the_release_composition_cannot_pull(tmp_path: Path) -> None:
    digests = {
        name: "sha256:" + (name.encode().hex() * 64)[:64]
        for name in ("backend", "frontend", "proxy", "backup", "postgres", "keycloak")
    }
    release = tmp_path / "compose.release.yaml"
    release.write_text(
        rc.render((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"), "v1.2.0", digests),
        encoding="utf-8",
    )
    env_file = write_synthetic_env(tmp_path / "synthetic.env", compose_file=release)
    remove_cached_project_images()
    args = ["docker", "compose", "-f", str(release), "--env-file", str(env_file)]
    pulled = run([*args, "pull", "backend"], no_credential(tmp_path), 300)
    assert pulled.returncode != 0, pulled.stdout + pulled.stderr
