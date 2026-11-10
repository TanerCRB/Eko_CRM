"""EKO-1-12 K-01: accepted same-ID custom JPA provider and image artifacts."""

import re
from typing import Any

import pytest

from tests.support.repo import REPO_ROOT, tracked_files

PROVIDER = REPO_ROOT / "identity" / "provider"
JAVA = PROVIDER / "src" / "main" / "java" / "org" / "eko_crm" / "keycloak" / "events"
DOCKERFILE = REPO_ROOT / "identity" / "Dockerfile"
OFFICIAL_FROM = "FROM quay.io/keycloak/keycloak:26.8.1"
BEHAVIOR_TEST_CLASS = "org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderTest"


def test_k01_custom_provider_is_same_id_higher_order_jpa_subtype() -> None:
    store = (JAVA / "FilteringJpaEventStoreProvider.java").read_text(encoding="utf-8")
    factory = (JAVA / "FilteringJpaEventStoreProviderFactory.java").read_text(encoding="utf-8")
    registration = (
        PROVIDER
        / "src"
        / "main"
        / "resources"
        / "META-INF"
        / "services"
        / "org.keycloak.events.EventStoreProviderFactory"
    ).read_text(encoding="utf-8")
    assert "extends JpaEventStoreProvider" in store
    assert "super.onEvent(event)" in store
    assert "event.getDetails().remove(Details.CODE_ID)" in store
    # G-01/S-01 (ADR-0005 addendum 2026-11-05, ADR-0007-C5): the versioned provider names the
    # destination enforcement itself — the accepted exceptions are keyed on the application realm,
    # and the prohibited fields are cleared outside them before the single inherited persist.
    assert "event.setSessionId(null)" in store
    assert "event.getDetails().remove(Details.USERNAME)" in store
    assert "user_not_found" in store
    assert "event.clone()" not in store
    assert "extends JpaEventStoreProviderFactory" in factory
    assert "int order()" in factory and "return 100" in factory
    assert "new FilteringJpaEventStoreProvider" in factory
    assert registration.strip() == (
        "org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory"
    )
    assert 'String ID = "jpa"' not in factory
    assert "EventListenerProvider" not in store


def stages(text: str) -> tuple[str, str]:
    """The Maven build stage and the final Keycloak stage, split at the official base line."""
    split = text.index(OFFICIAL_FROM)
    return text[:split], text[split:]


def providers_copy_lines(text: str) -> list[str]:
    return [
        line
        for line in stages(text)[1].splitlines()
        if line.startswith("COPY") and "/opt/keycloak/providers" in line
    ]


def final_line_of(text: str, startswith: str, contains: str) -> int:
    """Index of the unique final-stage line matching both fragments; absence is a failure."""
    matches = [
        index
        for index, line in enumerate(stages(text)[1].splitlines())
        if line.startswith(startswith) and contains in line
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one final-stage {contains!r} {startswith!r} line")
    return matches[0]


def assert_provider_before_build(text: str) -> None:
    assert final_line_of(text, "COPY", "/opt/keycloak/providers") < final_line_of(
        text, "RUN", "kc.sh build --spi-events-store--provider=jpa"
    )


def test_k01_custom_image_builds_java21_provider_before_selecting_jpa() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "maven:3.9.14-eclipse-temurin-21" in text
    assert OFFICIAL_FROM in text
    assert "/opt/keycloak/providers" in text
    assert "kc.sh build --spi-events-store--provider=jpa" in text
    assert_provider_before_build(text)
    assert "latest" not in text


def test_k01_providers_copy_is_owned_by_keycloak_and_world_readable() -> None:
    copy_lines = providers_copy_lines(DOCKERFILE.read_text(encoding="utf-8"))
    assert len(copy_lines) == 1
    assert "--chown=keycloak:keycloak" in copy_lines[0]
    assert "--chmod=644" in copy_lines[0]


def test_k01_final_stage_keeps_only_the_supported_shape() -> None:
    _, final = stages(DOCKERFILE.read_text(encoding="utf-8"))
    # The accepted final-image shape: provider JAR before kc.sh build, nothing else.
    assert "java -cp" not in final
    assert "test-classes" not in final
    assert "/opt/keycloak/lib" not in final
    assert "kc.sh build --spi-events-store--provider=jpa" in final


def run_commands(text: str) -> list[str]:
    """The full RUN commands of a Dockerfile, continuations joined."""
    commands: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if current is not None:
            if stripped.endswith("\\"):
                current.append(stripped[:-1])
            else:
                current.append(stripped)
                commands.append(" ".join(current))
                current = None
        elif stripped.startswith("RUN "):
            if stripped.endswith("\\"):
                current = [stripped[:-1]]
            else:
                commands.append(stripped)
    return commands


def test_k01_behavior_test_runs_in_the_maven_stage_and_fails_the_build() -> None:
    build, final = stages(DOCKERFILE.read_text(encoding="utf-8"))
    # The behavior test executes against the pinned 26.8.1 Maven-resolved dependencies inside a
    # single RUN of the build stage: package, classpath, test. A non-zero test exit fails that
    # RUN and therefore the image build.
    test_runs = [
        command
        for command in run_commands(build)
        if BEHAVIOR_TEST_CLASS in command
    ]  # fmt: skip
    assert len(test_runs) == 1
    command = test_runs[0]
    assert "mvn -q package" in command
    assert "dependency:build-classpath" in command
    assert "target/classes:target/test-classes:" in command
    assert not any(BEHAVIOR_TEST_CLASS in command for command in run_commands(final))
    assert BEHAVIOR_TEST_CLASS not in final


def test_k01_no_versioned_artifact_globs_keycloak_lib_internals() -> None:
    forbidden = re.compile("java " + "-cp" + r"[^\n]*/opt/keycloak" + "/lib")
    offenders = []
    for relative in tracked_files():
        path = REPO_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if forbidden.search(text):
            offenders.append(relative)
    assert offenders == []
    for path in (REPO_ROOT / "identity").rglob("*"):
        if path.is_file():
            assert "/opt/keycloak/lib" not in path.read_text(encoding="utf-8"), path


def test_k01_compose_uses_custom_image_without_adding_state_or_services(
    compose_source: dict[str, Any], rendered_shared: dict[str, Any]
) -> None:
    keycloak = compose_source["services"]["keycloak"]
    assert keycloak["build"]["context"] == "./identity"
    assert keycloak["image"] == "localhost/eko-crm/keycloak:26.8.1-eko112"
    assert len(compose_source["services"]) == 9
    assert len(rendered_shared["services"]) == 8
    assert set(compose_source["volumes"]) == {"pgdata", "proxy-data"}


def test_k01_provider_has_real_pre_persist_behavior_test() -> None:
    test = (
        PROVIDER
        / "src"
        / "test"
        / "java"
        / "org"
        / "eko_crm"
        / "keycloak"
        / "events"
        / "FilteringJpaEventStoreProviderTest.java"
    ).read_text(encoding="utf-8")
    assert "EntityManager" in test
    assert "new FilteringJpaEventStoreProvider(null, entityManager()).onEvent(event)" in test
    assert "getDetailsJson" in test
    assert "subsequent local delivery" in test


def test_k01_floating_or_unselected_custom_image_fails_static_checks() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    floating = text.replace(
        "quay.io/keycloak/keycloak:26.8.1", "quay.io/keycloak/keycloak:" + "latest"
    )
    assert "quay.io/keycloak/keycloak:26.8.1" not in floating
    unselected = text.replace(" --spi-events-store--provider=jpa", "")
    assert "kc.sh build --spi-events-store--provider=jpa" not in unselected


def test_k01_provider_after_build_or_final_stage_test_run_fails_static_checks() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    copy_lines = providers_copy_lines(text)
    assert len(copy_lines) == 1
    # Moving the only providers COPY after the accepted build line breaks the order assertion.
    moved = text.replace(copy_lines[0] + "\n", "", 1).replace(
        "kc.sh build --spi-events-store--provider=jpa\n",
        "kc.sh build --spi-events-store--provider=jpa\n" + copy_lines[0] + "\n",
        1,
    )
    assert moved != text
    with pytest.raises(AssertionError):
        assert_provider_before_build(moved)
    # A providers COPY removed entirely fails rather than passing through absence.
    without_provider = text.replace(copy_lines[0] + "\n", "", 1)
    with pytest.raises(AssertionError):
        assert_provider_before_build(without_provider)
