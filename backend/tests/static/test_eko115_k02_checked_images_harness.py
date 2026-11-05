"""EKO-1-15 K-02: in a release run the runtime harness runs the checked images, never a rebuild.

With EKO_CHECKED_IMAGES set, every composition the runtime tests start has no `build:` for the
four project images and runs the named checked images; without it, nothing changes.
"""

from pathlib import Path
from typing import Any

import pytest

from tests.runtime import conftest as harness
from tests.support.repo import render

CHECKED = {name: f"eko-crm/{name}:checked" for name in ("backend", "frontend", "proxy", "backup")}
GIVEN = " ".join(f"{name}={image}" for name, image in CHECKED.items())


def rendered_with(override: Path | None, env_file: Path) -> dict[str, Any]:
    if override is None:
        return render(env_file, dev_profile=True)
    return render(env_file, dev_profile=True, compose_file=None, extra_files=[override])


def test_eko115_k02_harness_uses_the_checked_images(
    monkeypatch: pytest.MonkeyPatch, synthetic_env: Path
) -> None:
    monkeypatch.setenv("EKO_CHECKED_IMAGES", GIVEN)
    harness.checked_images_override.cache_clear()
    override = harness.checked_images_override()
    assert override is not None
    services = rendered_with(override, synthetic_env)["services"]
    for service, name in harness.CHECKED_SERVICES.items():
        assert services[service]["image"] == CHECKED[name], service
        assert "build" not in services[service], service
        assert services[service]["pull_policy"] == "never", service
    composition = harness.Composition("p", synthetic_env)
    assert str(override) in composition.base_args()


def test_eko115_k02_contrast_without_the_variable_nothing_changes(
    monkeypatch: pytest.MonkeyPatch, synthetic_env: Path
) -> None:
    monkeypatch.delenv("EKO_CHECKED_IMAGES", raising=False)
    harness.checked_images_override.cache_clear()
    assert harness.checked_images_override() is None
    assert "-f" not in harness.Composition("p", synthetic_env).base_args()


def test_eko115_k02_harness_refuses_an_incomplete_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EKO_CHECKED_IMAGES", "backend=eko-crm/backend:checked")
    harness.checked_images_override.cache_clear()
    with pytest.raises(ValueError):
        harness.checked_images_override()
    harness.checked_images_override.cache_clear()
