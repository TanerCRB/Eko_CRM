"""EKO-1-15 K-06 / ADR-0004-C13, Reviewer R-02: the override the C13 previous-release half starts
`backend` with runs the given image as given. `backend` builds on `up` (`build:`,
`pull_policy: build`), so an override that only replaces `image:` rebuilds the head's source under
the previous release's name in `ci.yml` (no EKO_CHECKED_IMAGES); the override resets `build` and
never pulls or builds, as tests/runtime/eko113.py `backend_as` does.
"""

from pathlib import Path
from typing import Any, cast

import yaml

from tests.runtime.conftest import Composition
from tests.runtime.lab import Lab, PsqlSession
from tests.support.repo import REPO_ROOT

PREVIOUS = "ghcr.io/tanercrb/eko-crm/backend:v1.2.0@sha256:" + "1" * 64


def read_override(text: str) -> dict[str, Any]:
    """An override as Compose reads it; `!reset null` (unknown to PyYAML) read as "!reset"."""
    loaded: dict[str, Any] = yaml.safe_load(text.replace("!reset null", "'!reset'"))
    return loaded


def lab(tmp_path: Path) -> Lab:
    return Lab(
        composition=Composition("eko-test", tmp_path / "env"),
        workdir=tmp_path,
        shipped_image="localhost/eko-crm/backend:x",
        prober="prober",
        monitor=cast(PsqlSession, None),
    )


def override(composition: Composition) -> dict[str, Any]:
    [file] = composition.extra_files
    loaded: dict[str, Any] = read_override(file.read_text(encoding="utf-8"))
    return loaded


def test_eko115_k06_c13_backend_override_runs_the_previous_image_as_given(tmp_path: Path) -> None:
    service = override(lab(tmp_path)._with_image("backend", PREVIOUS))["services"]["backend"]
    assert service == {"image": PREVIOUS, "build": "!reset", "pull_policy": "never"}


def test_eko115_k06_c13_contrast_backend_builds_in_the_repository_composition() -> None:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    backend = compose["services"]["backend"]
    assert "build" in backend and backend["pull_policy"] == "build"


def test_eko115_k06_c13_migrate_override_is_unchanged_but_never_pulled(tmp_path: Path) -> None:
    service = override(lab(tmp_path)._with_image("migrate", PREVIOUS))["services"]["migrate"]
    assert service == {"image": PREVIOUS, "pull_policy": "never"}
