"""EKO-2-01 K-07 / ADR-0004-C35, static half: how the theme enters the custom image, and that
no rendered profile mounts over Keycloak's theme or provider directories or disables caching.

The built image itself (its added files, their writability, the byte-for-byte copy) is read in
`tests/runtime/test_eko201_k07_theme_image.py`.
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.support.repo import REPO_ROOT, render
from tests.support.theme_checks import DOCKERFILE, IMAGE_THEME_DIR, THEME_NAME

OFFICIAL_FROM = "FROM quay.io/keycloak/keycloak:26.8.1"
KEYCLOAK_DIRECTORIES = ("/opt/keycloak/themes", "/opt/keycloak/providers")
CACHE_SETTING = re.compile(
    r"(?i)(cache[-_]*themes|cache[-_]*templates|static[-_]*max[-_]*age|THEME__CACHE|"
    r"THEME_CACHE|CACHE_THEMES|CACHE_TEMPLATES|STATIC_MAX_AGE)"
)


def final_stage(text: str) -> list[str]:
    return text[text.index(OFFICIAL_FROM) :].splitlines()


def dockerfile_violations(text: str) -> list[str]:
    """The final stage adds exactly the provider JAR and the theme, the theme before the build,
    owned by root and with no group or other write permission (the runtime user is uid 1000 in
    group 0)."""
    lines = final_stage(text)
    problems: list[str] = []
    copies = [line for line in lines if re.match(r"(?i)^\s*(COPY|ADD)\b", line)]
    theme = [line for line in copies if IMAGE_THEME_DIR in line]
    provider = [line for line in copies if "/opt/keycloak/providers/" in line]
    extra = [line for line in copies if line not in theme and line not in provider]
    problems.extend(f"extra file copied into the image: {line.strip()}" for line in extra)
    if len(theme) != 1:
        return problems + [f"expected one theme COPY, found {len(theme)}"]
    copy = theme[0]
    if not re.search(rf"\sthemes/{THEME_NAME}/?\s+{IMAGE_THEME_DIR}/?\s*$", copy):
        problems.append(f"theme COPY source or target: {copy.strip()}")
    if "--chown=root:root" not in copy:
        problems.append("theme COPY not owned by root")
    mode = re.search(r"--chmod=(\S+)", copy)
    if (
        mode is None
        or not re.fullmatch(r"0?[0-7][0-5][0-5]", mode.group(1))
        or any(digit in "2367" for digit in mode.group(1)[-2:])
    ):
        problems.append("theme COPY mode is missing or grants group/other write")
    build = [index for index, line in enumerate(lines) if "kc.sh build" in line]
    if len(build) != 1 or lines.index(copy) > build[0]:
        problems.append("theme COPY is not before kc.sh build")
    if re.search(r"(?im)^\s*(VOLUME)\b", "\n".join(lines)):
        problems.append("final stage declares a VOLUME")
    return problems


def test_c35_dockerfile_adds_only_the_provider_and_the_theme_before_the_build() -> None:
    assert dockerfile_violations(DOCKERFILE.read_text(encoding="utf-8")) == []


def dockerfile_with(change: Callable[[str], str]) -> str:
    original = DOCKERFILE.read_text(encoding="utf-8")
    changed = change(original)
    assert changed != original, "fixture premise: the change applies"
    return changed


def add_line_before_build(line: str) -> Callable[[str], str]:
    return lambda text: text.replace("RUN touch -d", line + "\nRUN touch -d", 1)


def theme_copy(text: str) -> str:
    return next(line for line in text.splitlines() if IMAGE_THEME_DIR in line)


def group_writable(text: str) -> str:
    copy = theme_copy(text)
    return text.replace(copy, re.sub(r"--chmod=\S+", "--chmod=775", copy))


DOCKERFILE_FIXTURES = [
    ("extra-file", add_line_before_build("COPY eko-realm.json /opt/keycloak/data/import/")),
    ("extra-add", add_line_before_build("ADD theme-review.md /opt/keycloak/")),
    ("group-writable", group_writable),
    ("runtime-owned", lambda text: text.replace("--chown=root:root", "--chown=keycloak:keycloak")),
    ("after-build", lambda text: text.replace(theme_copy(text) + "\n", "", 1).replace(
        "USER root\n", theme_copy(text) + "\nUSER root\n", 1)),
    ("removed", lambda text: text.replace(theme_copy(text) + "\n", "", 1)),
]  # fmt: skip


@pytest.mark.parametrize(
    "change", [pytest.param(change, id=name) for name, change in DOCKERFILE_FIXTURES]
)
def test_c35_each_dockerfile_fixture_fails(change: Callable[[str], str]) -> None:
    assert dockerfile_violations(dockerfile_with(change)) != []


# Rendered profiles ---------------------------------------------------------------------------


def mount_violations(rendered: dict[str, Any]) -> list[str]:
    problems = []
    for name, service in rendered["services"].items():
        for volume in service.get("volumes") or []:
            target = str(volume.get("target", "")).rstrip("/")
            for directory in KEYCLOAK_DIRECTORIES:
                if (
                    target == directory
                    or directory.startswith(target + "/")
                    or target.startswith(directory + "/")
                ):
                    problems.append(f"{name}: {volume.get('type')} mount at {target}")
    return problems


def caching_violations(rendered: dict[str, Any]) -> list[str]:
    problems = []
    for name, service in rendered["services"].items():
        environment = service.get("environment") or {}
        for key, value in environment.items():
            if CACHE_SETTING.search(key) or CACHE_SETTING.search(str(value or "")):
                problems.append(f"{name}: environment {key}")
        for part in [*(service.get("command") or []), *(service.get("entrypoint") or [])]:
            if CACHE_SETTING.search(str(part)) or "start-dev" in str(part):
                problems.append(f"{name}: argument {part}")
    keycloak = rendered["services"].get("keycloak", {})
    if keycloak.get("command") != ["start"]:
        problems.append(f"keycloak: command {keycloak.get('command')}")
    return problems


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_c35_no_rendered_profile_mounts_over_theme_or_provider_or_disables_caching(
    synthetic_env: Path, profile: str
) -> None:
    rendered = render(synthetic_env, dev_profile=profile == "dev")
    assert "keycloak" in rendered["services"]
    assert mount_violations(rendered) == []
    assert caching_violations(rendered) == []


def compose_with(tmp_path: Path, old: str, new: str) -> Path:
    text = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert text.count(old) == 1, f"fixture premise: {old!r}"
    target = tmp_path / "compose.yaml"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return target


BOOT_VOLUME = (
    "      - keycloak-boot:/etc/eko/keycloak-boot\n    environment:\n      KC_DB: postgres\n"
)


def with_mount(line: str) -> str:
    return BOOT_VOLUME.replace("    environment:", f"      - {line}\n    environment:")


COMPOSE_FIXTURES = [
    (
        "bind-mount-theme",
        BOOT_VOLUME,
        with_mount("./identity/themes/eko-crm:/opt/keycloak/themes/eko-crm"),
        mount_violations,
    ),
    (
        "named-volume-theme",
        BOOT_VOLUME,
        with_mount("keycloak-boot:/opt/keycloak/themes"),
        mount_violations,
    ),
    (
        "bind-mount-providers",
        BOOT_VOLUME,
        with_mount("./identity/provider:/opt/keycloak/providers"),
        mount_violations,
    ),
    (
        "caching-disabled-environment",
        "      KC_DB: postgres\n",
        '      KC_DB: postgres\n      KC_SPI_THEME__CACHE_THEMES: "false"\n',
        caching_violations,
    ),
    (
        "caching-disabled-argument",
        '    command: ["start"]\n',
        '    command: ["start", "--spi-theme--cache-templates=false"]\n',
        caching_violations,
    ),
    (
        "development-start",
        '    command: ["start"]\n',
        '    command: ["start-dev"]\n',
        caching_violations,
    ),
]


@pytest.mark.parametrize("profile", ["dev", "shared"])
@pytest.mark.parametrize(
    ("old", "new", "check"),
    [pytest.param(old, new, check, id=name) for name, old, new, check in COMPOSE_FIXTURES],
)
def test_c35_each_composition_fixture_fails_naming_it(
    tmp_path: Path,
    synthetic_env: Path,
    profile: str,
    old: str,
    new: str,
    check: Callable[[dict[str, Any]], list[str]],
) -> None:
    rendered = render(
        synthetic_env, dev_profile=profile == "dev", compose_file=compose_with(tmp_path, old, new)
    )
    found = check(rendered)
    assert any(item.startswith("keycloak:") for item in found), found
