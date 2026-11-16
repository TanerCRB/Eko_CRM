"""EKO-2-01 B-04: every Maven plugin the identity image's `mvn` calls invoke by goal prefix
(`<prefix>:<goal>`, today `dependency:go-offline` and `dependency:build-classpath`) is declared in
`identity/provider/pom.xml` (`<build><plugins>` or `<build><pluginManagement><plugins>`; Maven
3.9.14 takes the version of a prefix-invoked plugin from either, evidence R21) with a literal, exact
version. A version range, `LATEST`, `RELEASE` or a property reference leaves the version to
something other than the pom line under review, so each is named.

The lifecycle phase (`package`) is bound by the digest-pinned Maven builder's default bindings,
which `test_eko201_dockerfile_pins.py` pins; this module covers the goals named by prefix. Not
covered: the prefix-to-artifact mapping, which Maven still reads from the org.apache.maven.plugins
group metadata of Maven Central (evidence R21).
"""

import re

import pytest

from tests.static.test_eko112_k01_custom_provider_image import run_commands
from tests.support.repo import REPO_ROOT
from tests.support.theme_checks import DOCKERFILE

POM = REPO_ROOT / "identity" / "provider" / "pom.xml"
APACHE_PLUGINS = "org.apache.maven.plugins"
# The version Maven 3.9.14's super POM (maven-model-builder-3.9.14.jar, pom-4.0.0.xml,
# pluginManagement) already gave maven-dependency-plugin before the pin: the pin does not change
# which plugin runs (evidence R21).
DEPENDENCY_PLUGIN_VERSION = "3.7.0"
EXACT_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
PREFIX_GOAL = re.compile(r"^([a-z][a-z0-9-]*):([a-z][a-z0-9-]*)$")
# The pom is a tracked file read as text (no XML parser, no new dependency): comments and a
# plugin's nested sections, whose <version> elements are not the plugin's, are removed first.
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
BUILD = re.compile(r"<build>(.*?)</build>", re.DOTALL)
PLUGIN = re.compile(r"<plugin>(.*?)</plugin>", re.DOTALL)
NESTED = re.compile(
    r"<dependencies>.*?</dependencies>|<executions>.*?</executions>"
    r"|<configuration>.*?</configuration>",
    re.DOTALL,
)


def invoked_plugins(dockerfile: str) -> list[str]:
    """The artifact IDs of the plugins the Dockerfile's `mvn` calls invoke by goal prefix, in
    first-use order. The Apache plugin naming convention maps prefix `p` to `maven-p-plugin`."""
    found: list[str] = []
    for command in run_commands(dockerfile):
        for part in re.split(r"&&|\|\||;", command.removeprefix("RUN ")):
            tokens = part.split()
            if not tokens or tokens[0] != "mvn":
                continue
            for token in tokens[1:]:
                match = PREFIX_GOAL.fullmatch(token)
                if match:
                    artifact = f"maven-{match.group(1)}-plugin"
                    if artifact not in found:
                        found.append(artifact)
    return found


def build_plugin_versions(pom: str) -> dict[str, str | None]:
    """Plugins of the Apache plugin group declared under `<build>` (directly or managed):
    artifact ID -> version text."""
    versions: dict[str, str | None] = {}
    for build in BUILD.findall(COMMENT.sub("", pom)):
        for plugin in PLUGIN.findall(build):
            own = NESTED.sub("", plugin)
            group = element(own, "groupId") or APACHE_PLUGINS
            artifact = element(own, "artifactId")
            if group == APACHE_PLUGINS and artifact:
                versions[artifact] = element(own, "version")
    return versions


def element(text: str, name: str) -> str | None:
    """The stripped text of the first `<name>` element in `text`, or None when absent."""
    match = re.search(rf"<{name}>(.*?)</{name}>", text, re.DOTALL)
    return match.group(1).strip() if match else None


def unpinned(dockerfile: str, pom: str) -> list[str]:
    """One finding per invoked plugin without an exact literal version; empty is the only pass."""
    invoked = invoked_plugins(dockerfile)
    if not invoked:
        return ["<no mvn goal invoked by prefix>"]
    declared = build_plugin_versions(pom)
    findings: list[str] = []
    for artifact in invoked:
        if artifact not in declared:
            findings.append(f"{artifact}: not declared in <build>")
            continue
        version = declared[artifact]
        if not version:
            findings.append(f"{artifact}: no version")
        elif not EXACT_VERSION.fullmatch(version):
            findings.append(f"{artifact}: not an exact version: {version}")
    return findings


def test_every_prefix_invoked_plugin_has_an_exact_version_in_the_pom() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pom = POM.read_text(encoding="utf-8")
    assert invoked_plugins(dockerfile) == ["maven-dependency-plugin"]
    assert unpinned(dockerfile, pom) == []


def test_the_dependency_plugin_keeps_the_version_the_builder_already_resolved() -> None:
    versions = build_plugin_versions(POM.read_text(encoding="utf-8"))
    assert versions.get("maven-dependency-plugin") == DEPENDENCY_PLUGIN_VERSION


PINNED_LINE = f"<version>{DEPENDENCY_PLUGIN_VERSION}</version>"


@pytest.mark.parametrize(
    ("replacement", "finding"),
    [
        pytest.param("", "maven-dependency-plugin: no version", id="version-removed"),
        pytest.param(
            "<version>[3.7,)</version>",
            "maven-dependency-plugin: not an exact version: [3.7,)",
            id="range",
        ),
        pytest.param(
            "<version>LATEST</version>",
            "maven-dependency-plugin: not an exact version: LATEST",
            id="latest",
        ),
        pytest.param(
            "<version>RELEASE</version>",
            "maven-dependency-plugin: not an exact version: RELEASE",
            id="release",
        ),
        pytest.param(
            "<version>${dependency.plugin.version}</version>",
            "maven-dependency-plugin: not an exact version: ${dependency.plugin.version}",
            id="property",
        ),
    ],
)
def test_each_unpinned_version_contrast_is_named(replacement: str, finding: str) -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pom = POM.read_text(encoding="utf-8")
    assert pom.count(PINNED_LINE) == 1, "fixture premise"
    assert unpinned(dockerfile, pom.replace(PINNED_LINE, replacement)) == [finding]


def test_a_pom_without_the_plugin_is_named_and_a_managed_pin_is_accepted() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pom = POM.read_text(encoding="utf-8")
    assert pom.count("<build>") == 1, "fixture premise"
    stripped = pom[: pom.index("<build>")] + pom[pom.index("</build>") + len("</build>") :]
    assert unpinned(dockerfile, stripped) == ["maven-dependency-plugin: not declared in <build>"]
    managed = pom.replace("<plugins>", "<pluginManagement><plugins>", 1).replace(
        "</plugins>", "</plugins></pluginManagement>", 1
    )
    assert managed != pom, "fixture premise"
    assert unpinned(dockerfile, managed) == []
    loose = managed.replace(PINNED_LINE, "<version>[3.7,)</version>")
    assert unpinned(dockerfile, loose) == ["maven-dependency-plugin: not an exact version: [3.7,)"]


def test_a_new_prefix_goal_in_the_dockerfile_is_named() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pom = POM.read_text(encoding="utf-8")
    planted = dockerfile.replace(
        "RUN mvn -q dependency:go-offline", "RUN mvn -q dependency:go-offline help:effective-pom"
    )
    assert planted != dockerfile, "fixture premise"
    assert unpinned(planted, pom) == ["maven-help-plugin: not declared in <build>"]


def test_a_version_only_in_a_nested_section_or_a_comment_is_not_a_pin() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pom = POM.read_text(encoding="utf-8")
    assert pom.count(PINNED_LINE) == 1, "fixture premise"
    nested = pom.replace(
        PINNED_LINE,
        "<dependencies><dependency><groupId>org.example</groupId><artifactId>synthetic</artifactId>"
        f"{PINNED_LINE}</dependency></dependencies>",
    )
    assert unpinned(dockerfile, nested) == ["maven-dependency-plugin: no version"]
    commented = pom.replace(PINNED_LINE, f"<!-- {PINNED_LINE} -->")
    assert unpinned(dockerfile, commented) == ["maven-dependency-plugin: no version"]
