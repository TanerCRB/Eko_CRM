"""EKO-2-01 B-02: both `FROM` lines of the custom Keycloak image name their base by version tag
and `@sha256:` digest, as `proxy/Dockerfile` does, so a moved upstream tag cannot change what the
same commit builds. The Keycloak base digest is the index the human accepted on 2026-11-13; the
Maven builder digest is the index this host built with (both recorded in the evidence)."""

import re

import pytest

from tests.support.theme_checks import DOCKERFILE, base_version

KEYCLOAK_BASE = (
    "quay.io/keycloak/keycloak:26.8.1"
    "@sha256:3f3c5f8e03c614774b4bd9173b88391fefa4153bfc010d8012d59ad825377332"
)
MAVEN_BUILDER = (
    "maven:3.9.14-eclipse-temurin-21"
    "@sha256:98819eb3745bd2007c3f1a19b59085c1fa3929aecb7dbfa431dfcf5a4f18ce3c"
)
PINNED = re.compile(r"^[^@\s]+:[^@\s]+@sha256:[0-9a-f]{64}$")


def from_references(text: str) -> list[str]:
    return [
        line.split()[1] for line in text.splitlines() if line.strip().upper().startswith("FROM ")
    ]


def unpinned(text: str) -> list[str]:
    references = from_references(text)
    if not references:
        return ["<no FROM line>"]
    return [reference for reference in references if not PINNED.fullmatch(reference)]


def test_both_from_lines_are_pinned_by_tag_and_digest() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert unpinned(text) == []
    assert from_references(text) == [MAVEN_BUILDER, KEYCLOAK_BASE]


def test_the_review_record_version_still_reads_the_pinned_base() -> None:
    assert base_version(DOCKERFILE.read_text(encoding="utf-8")) == "26.8.1"


@pytest.mark.parametrize(
    ("pinned", "contrast"),
    [
        pytest.param(KEYCLOAK_BASE, "quay.io/keycloak/keycloak:26.8.1", id="keycloak-tag-only"),
        pytest.param(MAVEN_BUILDER, "maven:3.9.14-eclipse-temurin-21", id="maven-tag-only"),
        pytest.param(KEYCLOAK_BASE, KEYCLOAK_BASE.replace(":26.8.1@", "@"), id="keycloak-no-tag"),
        pytest.param(KEYCLOAK_BASE, KEYCLOAK_BASE[:-1], id="keycloak-short-digest"),
    ],
)
def test_each_unpinned_contrast_fails_naming_the_reference(pinned: str, contrast: str) -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert text.count(pinned) == 1, "fixture premise"
    found = unpinned(text.replace(pinned, contrast))
    assert found == [contrast]
