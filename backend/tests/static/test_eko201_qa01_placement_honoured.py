"""EKO-2-01 QA-01 under EKO-1-26 route A: the Keycloak-runtime entry point honours placement.

`keycloak_client.build_keycloak` (called by `prepare` and the `built_image` fixture) reads the
composition the runtime harness renders — the checked-images override included, through the
harness's own `Composition.base_args` — and:

- placed (a release run: the keycloak service has its build reset to null and names the checked
  image): runs no `compose build keycloak`, and records and returns the placed image's ID;
- not placed (the development path: `build: ./identity` under the localhost anchor): builds the
  image from this tree, so a stale image behind the shared tag is replaced (QA-01).

The composition is rendered for real (`docker compose config`); only the build itself and the
image-ID lookup are recorded instead of run, so no image is built or read here.
"""

import ast
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.runtime import conftest as harness
from tests.runtime import keycloak_client
from tests.static import test_eko126_k02_bootstrap_checked_placement as bootstrap
from tests.support.bootstrap_placement import (
    PLACEMENT_VARIABLE,
    RUNNING_FAMILIES,
    bootstrap_placement,
)
from tests.support.repo import REPO_ROOT, render

CHECKED = {
    name: f"eko-crm/{name}:checked"
    for name in ("backend", "frontend", "proxy", "backup", "keycloak")
}
GIVEN = " ".join(f"{name}={image}" for name, image in CHECKED.items())
ANCHOR = "localhost/eko-crm/keycloak:26.8.1-eko112"
RUNTIME = REPO_ROOT / "backend" / "tests" / "runtime"


class Recording(harness.Composition):
    """Renders through the real harness; records every other compose call instead of running it."""

    calls: list[tuple[str, ...]]

    def compose(
        self, *args: str, check: bool = True, stdin: str | None = None, timeout: int = 300
    ) -> subprocess.CompletedProcess[str]:
        if args[:1] == ("config",):
            return super().compose(*args, check=check, stdin=stdin, timeout=timeout)
        self.calls.append(args)
        return subprocess.CompletedProcess([*self.base_args(), *args], 0, "", "")


def run_build(
    monkeypatch: pytest.MonkeyPatch, env_file: Path, placement: str | None
) -> tuple[Recording, str, list[str]]:
    if placement is None:
        monkeypatch.delenv("EKO_CHECKED_IMAGES", raising=False)
    else:
        monkeypatch.setenv("EKO_CHECKED_IMAGES", placement)
    harness.checked_images_override.cache_clear()
    looked_up: list[str] = []

    def fake_id(reference: str) -> str:
        looked_up.append(reference)
        return f"id-of:{reference}"

    monkeypatch.setattr(keycloak_client, "image_id", fake_id)
    composition = Recording(project="ekost-qa01p", env_file=env_file)
    composition.calls = []
    monkeypatch.delitem(keycloak_client.BUILT_KEYCLOAK, composition.project, raising=False)
    try:
        recorded = keycloak_client.build_keycloak(composition)
    finally:
        harness.checked_images_override.cache_clear()
    return composition, recorded, looked_up


def builds(calls: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    return [call for call in calls if "build" in call or "--build" in call]


def test_placed_keycloak_is_not_built_and_the_placed_image_is_recorded(
    monkeypatch: pytest.MonkeyPatch, synthetic_env: Path
) -> None:
    composition, recorded, looked_up = run_build(monkeypatch, synthetic_env, GIVEN)
    assert builds(composition.calls) == [], "the session built Keycloak under placement"
    assert looked_up == [CHECKED["keycloak"]]
    assert recorded == f"id-of:{CHECKED['keycloak']}"
    assert keycloak_client.BUILT_KEYCLOAK[composition.project] == recorded


def test_contrast_without_placement_keycloak_is_built_from_the_tree(
    monkeypatch: pytest.MonkeyPatch, synthetic_env: Path
) -> None:
    composition, recorded, looked_up = run_build(monkeypatch, synthetic_env, None)
    assert builds(composition.calls) == [("build", "keycloak")]
    assert looked_up == [ANCHOR]
    assert recorded == f"id-of:{ANCHOR}"
    assert keycloak_client.BUILT_KEYCLOAK[composition.project] == recorded


def compose_build_keycloak_calls(path: Path) -> list[str]:
    """`<x>.compose("build", "keycloak", ...)` calls in a file, by enclosing function name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "compose":
                continue
            literal: list[Any] = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
            if literal[:2] == ["build", "keycloak"]:
                found.append(function.name)
    return found


def test_the_runtime_harness_builds_keycloak_only_through_build_keycloak() -> None:
    """No other runtime path runs its own `compose build keycloak` past the placement check."""
    found = {
        f"{path.name}:{name}"
        for path in sorted(RUNTIME.glob("*.py"))
        for name in compose_build_keycloak_calls(path)
    }
    assert found == {"keycloak_client.py:build_keycloak"}


def test_contrast_a_planted_direct_build_is_named(tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def built_image(composition):\n"
        '    composition.compose("build", "keycloak", timeout=1800)\n',
        encoding="utf-8",
    )
    assert compose_build_keycloak_calls(planted) == ["built_image"]


# Option A (2026-11-15): the C36 no-provider contrast hands the bootstrap a placement --------------

FIXTURE = "localhost/eko-crm/eko201-fixture:no-provider-0000"


@pytest.mark.parametrize("placed", [False, True], ids=["build-mode", "release-mode"])
def test_bootstrap_placement_starts_keycloak_from_the_fixture_in_both_modes(
    placed: bool, tmp_path: Path, synthetic_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bootstrap, offline against EKO-1-26's recording double, given `bootstrap_placement` of
    the composition as the harness renders it (with or without the checked images placed):
    both its keycloak starts carry the placement override, and that override starts Keycloak from
    the fixture, with no build and no pull; every other family keeps the image it runs."""
    if placed:
        monkeypatch.setenv("EKO_CHECKED_IMAGES", GIVEN)
    else:
        monkeypatch.delenv("EKO_CHECKED_IMAGES", raising=False)
    harness.checked_images_override.cache_clear()
    try:
        override = harness.checked_images_override()
        rendered = render(
            synthetic_env,
            dev_profile=True,
            compose_file=None,
            extra_files=[override] if override else None,
        )
    finally:
        harness.checked_images_override.cache_clear()
    running = {name: image_of(rendered, name) for name in RUNNING_FAMILIES}
    given = bootstrap_placement(running, FIXTURE)
    run = bootstrap.run_bootstrap(
        tmp_path, synthetic_env, checked=given[PLACEMENT_VARIABLE], rerun=False
    )
    assert run["rc"] == 0, run["out"]
    starts = bootstrap.keycloak_up_lines(run["calls"])
    assert len(starts) == 2, run["calls"]
    for line in starts:
        assert "checked-images.yaml" in [Path(f).name for f in bootstrap.passed_files(line)]
    written = run["snap"] / "checked-images.yaml"
    placed_services = render(run["env_file"], dev_profile=True, extra_files=[written])["services"]
    keycloak = placed_services["keycloak"]
    assert keycloak["image"] == FIXTURE
    assert "build" not in keycloak and keycloak["pull_policy"] == "never"
    for family in RUNNING_FAMILIES:
        assert placed_services[family]["image"] == running[family], family


def image_of(rendered: dict[str, Any], service: str) -> str:
    """The image a container of `service` runs: its `image`, or the name Compose gives a build
    without one (`<project>-<service>`)."""
    given = rendered["services"][service].get("image")
    return str(given) if given else f"{rendered['name']}-{service}"


def test_contrast_bootstrap_placement_needs_every_running_family() -> None:
    """A rendering without one of the families the bootstrap requires is refused here, before a
    bootstrap that would refuse it later."""
    running = {family: f"example/{family}:x" for family in RUNNING_FAMILIES}
    assert bootstrap_placement(running, FIXTURE)[PLACEMENT_VARIABLE].split() == [
        "backend=example/backend:x",
        "frontend=example/frontend:x",
        "proxy=example/proxy:x",
        "backup=example/backup:x",
        f"keycloak={FIXTURE}",
    ]
    del running["backup"]
    with pytest.raises(KeyError):
        bootstrap_placement(running, FIXTURE)
