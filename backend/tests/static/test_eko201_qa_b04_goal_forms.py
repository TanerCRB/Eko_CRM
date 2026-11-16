"""EKO-2-01 B-04 (QA): the plugin-pin guard in `test_eko201_b04_plugin_pins.py` sees only goals
written as `<prefix>:<goal>` in a RUN part whose first token is exactly `mvn`. Two other ways to
make the identity build run a plugin escape it:

- a full-coordinates goal (`groupId:artifactId:goal`) - Maven then resolves the plugin version
  from repository metadata, which is the B-04 harm, and the guard ignores the token;
- a `mvn` call the guard does not recognise (a path such as `/usr/share/maven/bin/mvn`, the
  wrapper `mvnw`, or a leading `NAME=value` assignment) - its prefix goals are never checked.

This module reads every `mvn` call more broadly and names both. A full-coordinates goal that
carries an exact version (`groupId:artifactId:version:goal`) is pinned by itself and passes.

On the pom side the guard also accepts a pin inside `<profiles><profile><build>`, which Maven
applies only when that profile is active: with the 3.7.0 pin moved into an inactive profile as
3.6.1, the goal still ran as 3.7.0 from the builder's super POM (QA probe, 2026-11-15). The pin
must therefore hold with every profile removed.
"""

import re

import pytest

from tests.static.test_eko112_k01_custom_provider_image import run_commands
from tests.static.test_eko201_b04_plugin_pins import (
    COMMENT,
    EXACT_VERSION,
    POM,
    invoked_plugins,
    unpinned,
)
from tests.support.theme_checks import DOCKERFILE

MAVEN_COMMANDS = {"mvn", "mvnw"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ANCHOR = "RUN mvn -q dependency:go-offline"
PROFILES = re.compile(r"<profiles>.*?</profiles>", re.DOTALL)


def mvn_goals(dockerfile: str) -> list[str]:
    """Every goal-shaped token (contains `:`, not an option) of every `mvn`/`mvnw` call in a RUN
    command, whatever path or leading assignments the call carries, in order."""
    goals: list[str] = []
    for command in run_commands(dockerfile):
        for part in re.split(r"&&|\|\||;|\|", command.removeprefix("RUN ")):
            tokens = part.split()
            while tokens and (ASSIGNMENT.match(tokens[0]) or tokens[0] == "env"):
                tokens = tokens[1:]
            if not tokens or tokens[0].rsplit("/", 1)[-1] not in MAVEN_COMMANDS:
                continue
            goals.extend(t for t in tokens[1:] if ":" in t and not t.startswith("-"))
    return goals


def goal_findings(dockerfile: str) -> list[str]:
    """One finding per goal whose plugin version neither the pom guard nor the goal fixes."""
    guarded = set(invoked_plugins(dockerfile))
    findings: list[str] = []
    for goal in mvn_goals(dockerfile):
        parts = goal.split(":")
        if len(parts) == 2:
            if f"maven-{parts[0]}-plugin" not in guarded:
                findings.append(f"{goal}: prefix goal outside the pom guard's view")
        elif len(parts) == 3:
            findings.append(f"{goal}: full coordinates without a version")
        elif len(parts) == 4:
            if not EXACT_VERSION.fullmatch(parts[2]):
                findings.append(f"{goal}: not an exact version: {parts[2]}")
        else:
            findings.append(f"{goal}: unrecognised goal form")
    return findings


def test_every_mvn_goal_is_seen_by_the_pom_guard_or_pinned_by_itself() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert goal_findings(dockerfile) == []
    # Non-vacuity: the broad reader sees the two goals the build really runs.
    goals = mvn_goals(dockerfile)
    assert "dependency:go-offline" in goals
    assert "dependency:build-classpath" in goals


@pytest.mark.parametrize(
    ("planted", "findings"),
    [
        pytest.param(
            f"{ANCHOR} org.apache.maven.plugins:maven-help-plugin:effective-pom",
            [
                "org.apache.maven.plugins:maven-help-plugin:effective-pom: "
                "full coordinates without a version"
            ],
            id="full-coordinates-unversioned",
        ),
        pytest.param(
            f"{ANCHOR} org.apache.maven.plugins:maven-help-plugin:3.4.1:effective-pom",
            [],
            id="full-coordinates-exact-version-contrast",
        ),
        pytest.param(
            f"{ANCHOR} org.apache.maven.plugins:maven-help-plugin:LATEST:effective-pom",
            [
                "org.apache.maven.plugins:maven-help-plugin:LATEST:effective-pom: "
                "not an exact version: LATEST"
            ],
            id="full-coordinates-latest",
        ),
        pytest.param(
            f"{ANCHOR} && /usr/share/maven/bin/mvn -q help:effective-pom",
            ["help:effective-pom: prefix goal outside the pom guard's view"],
            id="mvn-by-path",
        ),
        pytest.param(
            f"{ANCHOR} && MAVEN_OPTS=-Xmx1g mvn -q help:effective-pom",
            ["help:effective-pom: prefix goal outside the pom guard's view"],
            id="mvn-after-assignment",
        ),
        pytest.param(
            f"{ANCHOR} && ./mvnw -q help:effective-pom",
            ["help:effective-pom: prefix goal outside the pom guard's view"],
            id="maven-wrapper",
        ),
        pytest.param(
            # Contrast: a plain `mvn` call is the pom guard's to name, not this one's.
            f"{ANCHOR} && mvn -q help:effective-pom",
            [],
            id="plain-mvn-contrast",
        ),
    ],
)
def test_each_goal_form_outside_the_pom_guard_is_named(planted: str, findings: list[str]) -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert dockerfile.count(ANCHOR + "\n") == 1, "fixture premise"
    changed = dockerfile.replace(ANCHOR + "\n", planted + "\n")
    assert goal_findings(changed) == findings


def without_profiles(pom: str) -> str:
    """The pom as Maven reads it when no profile is active."""
    return PROFILES.sub("", COMMENT.sub("", pom))


def test_the_pin_holds_with_every_profile_inactive() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert unpinned(dockerfile, without_profiles(POM.read_text(encoding="utf-8"))) == []


def test_a_pin_only_inside_a_profile_is_named_and_an_extra_profile_is_not() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pom = POM.read_text(encoding="utf-8")
    assert pom.count("  <build>") == 1 and pom.count("</build>") == 1, "fixture premise"
    start, end = pom.index("  <build>"), pom.index("</build>") + len("</build>")
    block = pom[start:end]
    in_profile = (
        pom[:start] + "<profiles><profile><id>pins</id>" + block + "</profile></profiles>"
    ) + pom[end:]
    # The pom guard alone accepts this; with profiles inactive the plugin is not declared.
    assert unpinned(dockerfile, in_profile) == []
    assert unpinned(dockerfile, without_profiles(in_profile)) == [
        "maven-dependency-plugin: not declared in <build>"
    ]
    extra = pom.replace(
        "</project>",
        "<profiles><profile><id>extra</id><build><plugins><plugin>"
        "<artifactId>maven-help-plugin</artifactId><version>3.5.1</version>"
        "</plugin></plugins></build></profile></profiles></project>",
    )
    assert extra != pom, "fixture premise"
    assert unpinned(dockerfile, without_profiles(extra)) == []
