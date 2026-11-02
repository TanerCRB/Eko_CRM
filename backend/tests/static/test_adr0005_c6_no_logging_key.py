"""EKO-1-13 K-06: no service of the rendered composition, in either profile, declares a `logging`
key, so every container log uses the driver its host's container runtime is configured with
(ADR-0005-C6 as restated by the deviation addendum of 2026-11-02, Q-7 H).

The service set of each profile is asserted first, so an empty or partial render cannot pass. The
source half catches `logging: {}` and `logging: null`, which the render may drop. This claims no
deletion: deleting by time on each shared host is EKO-1-08's (#36).
"""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support.compose_checks import DEV_SERVICES, SHARED_SERVICES
from tests.support.repo import render

COMPOSE = Path(__file__).resolve().parents[3] / "compose.yaml"
Rendered = dict[str, Any]


def rendered_problems(rendered: Rendered, expected: set[str], profile: str) -> list[str]:
    services: dict[str, Any] = rendered.get("services") or {}
    if set(services) != expected:
        return [f"{profile}: services {sorted(services)}, not {sorted(expected)}"]
    return [f"{profile}: {name} declares logging {service['logging']!r}"
            for name, service in sorted(services.items()) if "logging" in service]  # fmt: skip


def source_problems(source: dict[str, Any]) -> list[str]:
    services: dict[str, Any] = source.get("services") or {}
    return [f"source: {name} declares logging" for name, service in sorted(services.items())
            if isinstance(service, dict) and "logging" in service]  # fmt: skip


def no_logging_key_problems(dev: Rendered, shared: Rendered, source: dict[str, Any]) -> list[str]:
    return (
        rendered_problems(dev, DEV_SERVICES, "development")
        + rendered_problems(shared, SHARED_SERVICES, "shared")
        + source_problems(source)
    )


def test_adr0005_c6_no_logging_key(
    rendered_dev: Rendered, rendered_shared: Rendered, compose_source: dict[str, Any]
) -> None:
    assert no_logging_key_problems(rendered_dev, rendered_shared, compose_source) == []


# Planted fixture compositions: one service block given one logging declaration.
PLANTS = {
    "size-only-rotation": 'logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}',
    "time-option-above-14-days": 'logging: {driver: local, options: {max-age: "30d"}}',
    "cloud-driver": "logging: {driver: awslogs}",
    "driver-local-no-options": "logging: {driver: local}",
    "driver-json-file-no-options": "logging: {driver: json-file}",
    "options-without-driver": 'logging: {options: {max-size: "10m"}}',
    "empty": "logging: {}",
    "null": "logging: null",
}
SERVICE_LINE = {"shared": "  backup:\n", "mailcatcher": "  mailcatcher:\n"}


@pytest.fixture
def planted(tmp_path: Path, synthetic_env: Path) -> Callable[[str, str], list[str]]:
    def check(declaration: str, where: str) -> list[str]:
        text = COMPOSE.read_text(encoding="utf-8")
        line = SERVICE_LINE[where]
        assert text.count(line) == 1
        target = tmp_path / f"compose-{where}.yaml"
        target.write_text(text.replace(line, f"{line}    {declaration}\n"), encoding="utf-8")
        source = yaml.safe_load(target.read_text(encoding="utf-8"))
        try:
            dev = render(synthetic_env, dev_profile=True, compose_file=target)
            shared = render(synthetic_env, dev_profile=False, compose_file=target)
        except subprocess.CalledProcessError:
            # Compose refuses some declarations (`logging: null`) outright: the source half alone
            # must then catch them.
            return source_problems(source)
        return no_logging_key_problems(dev, shared, source)

    return check


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_adr0005_c6_no_logging_key_contrast_each_fixture_fails(
    planted: Callable[[str, str], list[str]], plant: str
) -> None:
    assert planted(PLANTS[plant], "shared") != []


def test_adr0005_c6_no_logging_key_contrast_mailcatcher_only(
    planted: Callable[[str, str], list[str]],
) -> None:
    problems = planted(PLANTS["size-only-rotation"], "mailcatcher")
    assert any(p.startswith("development: mailcatcher") for p in problems), problems


def test_adr0005_c6_no_logging_key_contrast_yaml_merge_of_an_extension(
    tmp_path: Path, synthetic_env: Path
) -> None:
    """A merge from an `x-` field puts no `logging` text in the service block; the render does."""
    text = COMPOSE.read_text(encoding="utf-8")
    text = text.replace(
        "services:\n", "x-logging: &logging-defaults\n  logging: {driver: local}\n\nservices:\n", 1
    ).replace("  worker:\n", "  worker:\n    <<: *logging-defaults\n", 1)
    target = tmp_path / "compose-merge.yaml"
    target.write_text(text, encoding="utf-8")
    shared = render(synthetic_env, dev_profile=False, compose_file=target)
    assert rendered_problems(shared, SHARED_SERVICES, "shared") != []


def test_adr0005_c6_no_logging_key_contrast_empty_render() -> None:
    assert rendered_problems({"services": {}}, SHARED_SERVICES, "shared") != []
