"""EKO-2-01 QA-01: the Keycloak-runtime entry point (`keycloak_client.prepare`, used by every
Keycloak fixture and carrier) builds the Keycloak image from the tree under test, so a stale
image behind the shared tag is never what the carriers run.

The stale image is a fixture: the current image with the theme removed, tagged over the shared
tag, as another worktree's older build would be. After `build_keycloak` the image the composition
runs Keycloak from is the recorded one, not the planted stale image, and its theme is the
repository's, byte for byte; `run_bootstrap`'s self-check refuses a running Keycloak that is not
that image. Without placement the composition runs the shared tag, so the build replaces the stale
image there; with the checked images placed (EKO-1-26) it runs the placed image and builds nothing.
The shared tag is restored to what it held before the plant, whatever happens.
"""

import secrets
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.runtime.conftest import Composition, make_env_file
from tests.runtime.keycloak_client import (
    BUILT_KEYCLOAK,
    assert_running_keycloak_is_the_built_one,
    build_keycloak,
    image_id,
    keycloak_image_reference,
)
from tests.runtime.test_eko201_k07_theme_image import IMAGE, image_theme
from tests.support import theme_checks as tc

pytestmark = pytest.mark.runtime


def docker(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=True
    )


def shared_tag_holder() -> str | None:
    """The image ID behind the shared tag, or None when the host has no such tag."""
    found = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return found.stdout.strip() if found.returncode == 0 else None


def restore_shared_tag(held: str | None) -> None:
    if held is None:
        subprocess.run(["docker", "image", "rm", IMAGE], capture_output=True, check=False)
        assert shared_tag_holder() is None, "the shared tag was left on the fixture image"
        return
    docker("tag", held, IMAGE)
    assert shared_tag_holder() == held, "the shared tag was not restored"


def test_qa01_prepare_replaces_a_stale_shared_tag_with_the_tree_build(tmp_path: Path) -> None:
    project = "ekort-qa01-" + uuid.uuid4().hex[:8]
    composition = Composition(project=project, env_file=make_env_file(tmp_path, project))
    current = build_keycloak(composition)
    assert tc.byte_differences(tc.repository_theme(), image_theme(current)) == []
    runs_from = keycloak_image_reference(composition)

    # Another worktree's older build behind the shared tag: no theme at all.
    (tmp_path / "Dockerfile").write_text(
        f"FROM {runs_from}\nUSER 0\nRUN rm -rf {tc.IMAGE_THEME_DIR}\nUSER 1000\n",
        encoding="utf-8",
    )
    stale_tag = f"localhost/eko-crm/eko201-fixture:stale-{secrets.token_hex(4)}"
    docker("build", "-q", "-t", stale_tag, str(tmp_path))
    held = shared_tag_holder()
    try:
        docker("tag", stale_tag, IMAGE)
        stale = image_id(IMAGE)
        assert stale != current
        assert (
            "eko-crm"
            not in docker("run", "--rm", "--entrypoint", "ls", IMAGE, "/opt/keycloak/themes").stdout
        ), "fixture premise: the stale image has no theme"

        rebuilt = build_keycloak(composition)
        assert rebuilt != stale, "prepare kept the stale image"
        assert image_id(runs_from) == rebuilt == BUILT_KEYCLOAK[project]
        assert tc.byte_differences(tc.repository_theme(), image_theme(rebuilt)) == []
    finally:
        # Put the shared tag back on what it held before the plant (or remove it if it held
        # nothing), whatever happened above; then drop the fixture.
        restore_shared_tag(held)
        subprocess.run(["docker", "rmi", "-f", stale_tag], capture_output=True, check=False)


def test_qa01_self_check_refuses_a_keycloak_that_is_not_the_built_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = "ekort-qa01b-" + uuid.uuid4().hex[:8]
    composition = Composition(project=project, env_file=make_env_file(tmp_path, project))
    with pytest.raises(AssertionError, match="not built by prepare"):
        assert_running_keycloak_is_the_built_one(composition)

    class Running(Composition):
        def compose(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(list(args), 0, "container-id\n", "")

        def inspect(self, service: str) -> dict[str, object]:
            return {"Image": "sha256:" + "1" * 64}

    running = Running(project=project, env_file=composition.env_file)
    monkeypatch.setitem(BUILT_KEYCLOAK, project, "sha256:" + "2" * 64)
    with pytest.raises(AssertionError, match="not the image built from this tree"):
        assert_running_keycloak_is_the_built_one(running)
    monkeypatch.setitem(BUILT_KEYCLOAK, project, "sha256:" + "1" * 64)
    assert_running_keycloak_is_the_built_one(running)
