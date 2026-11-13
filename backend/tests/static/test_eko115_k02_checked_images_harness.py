"""EKO-1-15 K-02: in a release run the runtime harness runs the checked images, never a rebuild.

With EKO_CHECKED_IMAGES set, every composition the runtime tests start has no `build:` for the
five project images and runs the named checked images, and the backup manifest names the placed
images the composition runs (EKO-1-26 K-02, C-4); without the variable nothing changes — the
development render keeps the custom Keycloak image's `build: ./identity` and its localhost anchor,
which the manifest names too (EKO-1-26 K-05: no registry on the development path).
"""

from pathlib import Path
from typing import Any

import pytest

from tests.runtime import conftest as harness
from tests.support.repo import REPO_ROOT, render

CHECKED = {
    name: f"eko-crm/{name}:checked"
    for name in ("backend", "frontend", "proxy", "backup", "keycloak")
}
GIVEN = " ".join(f"{name}={image}" for name, image in CHECKED.items())
KEYCLOAK_ANCHOR = "localhost/eko-crm/keycloak:26.8.1-eko112"


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
    # EKO-1-26 K-02 (C-4 edge): every name of the keycloak image in this composition is the one
    # placed — the service's and the backup manifest's alike.
    manifest = services["backup"]["environment"]
    assert manifest["BACKUP_MANIFEST_BACKEND_IMAGE"] == CHECKED["backend"]
    assert manifest["BACKUP_MANIFEST_KEYCLOAK_IMAGE"] == CHECKED["keycloak"]
    composition = harness.Composition("p", synthetic_env)
    assert str(override) in composition.base_args()


def test_eko115_k02_contrast_without_the_variable_nothing_changes(
    monkeypatch: pytest.MonkeyPatch, synthetic_env: Path
) -> None:
    monkeypatch.delenv("EKO_CHECKED_IMAGES", raising=False)
    harness.checked_images_override.cache_clear()
    assert harness.checked_images_override() is None
    assert "-f" not in harness.Composition("p", synthetic_env).base_args()
    # EKO-1-26 K-05 contrast half: the development path builds the custom image from ./identity
    # under its localhost anchor, and the manifest names that anchor — the reversed state of the
    # freeze above, from the same rendering call.
    services = rendered_with(None, synthetic_env)["services"]
    # Compose config fills the default `dockerfile` and resolves the context to the checkout's
    # `identity/` directory — the development build stays exactly the one EKO-1-12 shipped.
    assert Path(services["keycloak"]["build"]["context"]).resolve() == (REPO_ROOT / "identity")
    assert services["keycloak"]["image"] == KEYCLOAK_ANCHOR
    assert services["backup"]["environment"]["BACKUP_MANIFEST_KEYCLOAK_IMAGE"] == KEYCLOAK_ANCHOR


def test_eko115_k02_harness_refuses_an_incomplete_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EKO_CHECKED_IMAGES", "backend=eko-crm/backend:checked")
    harness.checked_images_override.cache_clear()
    with pytest.raises(ValueError):
        harness.checked_images_override()
    harness.checked_images_override.cache_clear()


def test_eko126_k02_harness_refuses_when_keycloak_is_not_placed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EKO-1-26 K-02 edge: a list holding the other four pairs and no keycloak pair is refused."""
    given = " ".join(f"{name}={image}" for name, image in CHECKED.items() if name != "keycloak")
    monkeypatch.setenv("EKO_CHECKED_IMAGES", given)
    harness.checked_images_override.cache_clear()
    with pytest.raises(ValueError):
        harness.checked_images_override()
    harness.checked_images_override.cache_clear()
