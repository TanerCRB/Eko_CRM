"""R-03: two checkouts on one Docker host never share a Compose project or a backend image tag.

Each checkout's generated environment file names its own project and its own image tag, both
derived from the checkout's path; the composition requires the project name and fixes neither.
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.static.conftest import COMPOSE
from tests.support.repo import render, write_synthetic_env

BACKEND_IMAGE_SERVICES = ("backend", "migrate", "worker")


def env_values(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line)


def other_checkout(tmp_path: Path) -> Path:
    copy = tmp_path / "Eko_CRM-OTHER" / "compose.yaml"
    copy.parent.mkdir()
    shutil.copy(COMPOSE, copy)
    return copy


def test_k01_project_name_is_a_required_variable(compose_source: dict[str, Any]) -> None:
    # R-06: neither fixed (R-03) nor left to the directory name; required, with no default.
    assert re.fullmatch(r"\$\{COMPOSE_PROJECT_NAME:\?[^}]*\}", str(compose_source.get("name")))


def test_k01_start_without_a_project_name_is_refused(tmp_path: Path) -> None:
    """A hand-written env file (a shared environment's) lacking the name: refused, naming it,
    instead of a project named after the deployment directory with a new, empty pgdata."""
    env_file = write_synthetic_env(tmp_path / "shared.env")
    values = env_values(env_file)
    del values["COMPOSE_PROJECT_NAME"]
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    for dev_profile in (False, True):
        with pytest.raises(subprocess.CalledProcessError) as refused:
            render(env_file, dev_profile=dev_profile)
        assert "COMPOSE_PROJECT_NAME" in refused.value.stderr


def test_k01_backend_image_tag_comes_from_a_required_variable(
    compose_source: dict[str, Any],
) -> None:
    for service in BACKEND_IMAGE_SERVICES:
        image = compose_source["services"][service]["image"]
        assert re.fullmatch(r"localhost/eko-crm/backend:\$\{BACKEND_IMAGE_TAG:\?[^}]*\}", image)


def test_k01_two_checkouts_get_different_projects_and_image_tags(tmp_path: Path) -> None:
    here = env_values(write_synthetic_env(tmp_path / "here.env"))
    there = env_values(write_synthetic_env(tmp_path / "there.env", other_checkout(tmp_path)))
    for name in ("COMPOSE_PROJECT_NAME", "BACKEND_IMAGE_TAG"):
        assert here[name] and there[name], name
        assert here[name] != there[name], name


def test_k01_one_checkout_always_gets_the_same_project(tmp_path: Path) -> None:
    first = env_values(write_synthetic_env(tmp_path / "a.env"))
    second = env_values(write_synthetic_env(tmp_path / "b.env"))
    assert first["COMPOSE_PROJECT_NAME"] == second["COMPOSE_PROJECT_NAME"]
    assert first["BACKEND_IMAGE_TAG"] == second["BACKEND_IMAGE_TAG"]


def test_k01_rendered_project_and_images_follow_the_env_file(tmp_path: Path) -> None:
    here_env = write_synthetic_env(tmp_path / "here.env")
    there_env = write_synthetic_env(tmp_path / "there.env", other_checkout(tmp_path))
    here = render(here_env, dev_profile=False)
    there = render(there_env, dev_profile=False)
    assert here["name"] != there["name"]
    for service in BACKEND_IMAGE_SERVICES:
        assert here["services"][service]["image"] != there["services"][service]["image"]
    assert here["name"] == env_values(here_env)["COMPOSE_PROJECT_NAME"]
