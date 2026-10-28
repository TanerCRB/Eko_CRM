"""Image-reference rules: ADR-0002-C12 as restated 2026-10-28, ADR-0003-C3, ADR-0004-C2."""

import re
from dataclasses import dataclass

POSTGRES_NAMES = {"postgres", "library/postgres", "docker.io/library/postgres"}
KEYCLOAK_NAMES = {"quay.io/keycloak/keycloak", "keycloak/keycloak", "docker.io/keycloak/keycloak"}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
POSTGRES_TAG = re.compile(r"18\.[0-9]+-(alpine[0-9]+\.[0-9]+|[a-z]+)")
FLOATING_ALPINE = re.compile(r"18\.[0-9]+-alpine")
KEYCLOAK_TAG = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
FULL_VERSION_TAG = re.compile(r"v?[0-9]+\.[0-9]+\.[0-9]+([-.+][0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class ImageRef:
    name: str
    tag: str | None
    digest: str | None


def parse(reference: str) -> ImageRef:
    rest, _, digest = reference.partition("@")
    # A colon after the last slash separates the tag; one before it belongs to a registry port.
    slash = rest.rfind("/")
    colon = rest.rfind(":")
    if colon > slash:
        return ImageRef(rest[:colon], rest[colon + 1 :], digest or None)
    return ImageRef(rest, None, digest or None)


def _digest_problems(ref: ImageRef) -> list[str]:
    if ref.digest is not None and not DIGEST.fullmatch(ref.digest):
        return [f"digest {ref.digest!r} is not sha256 with 64 lower-case hex digits"]
    return []


def postgres_violations(ref: ImageRef) -> list[str]:
    problems = _digest_problems(ref)
    if ref.tag is None:
        if ref.digest is None:
            problems.append("postgres reference with neither tag nor digest")
        return problems
    if "$" in ref.tag or "{" in ref.tag:
        problems.append(f"postgres tag {ref.tag!r} comes from a variable")
    elif FLOATING_ALPINE.fullmatch(ref.tag) or not POSTGRES_TAG.fullmatch(ref.tag):
        problems.append(f"postgres tag {ref.tag!r} is not 18.<minor>-<OS release>")
    return problems


def keycloak_violations(ref: ImageRef) -> list[str]:
    problems = _digest_problems(ref)
    if ref.tag is None:
        if ref.digest is None:
            problems.append("keycloak reference with neither tag nor digest")
    elif not KEYCLOAK_TAG.fullmatch(ref.tag):
        problems.append(f"keycloak tag {ref.tag!r} is not <major>.<minor>.<patch>")
    return problems


def generic_violations(ref: ImageRef) -> list[str]:
    problems = _digest_problems(ref)
    if ref.tag is None:
        if ref.digest is None:
            problems.append(f"{ref.name}: neither tag nor digest")
    elif not FULL_VERSION_TAG.fullmatch(ref.tag):
        problems.append(f"{ref.name}: tag {ref.tag!r} is not a full version")
    return problems


def image_ref_violations(reference: str) -> list[str]:
    ref = parse(reference.strip())
    if ref.name in POSTGRES_NAMES:
        return postgres_violations(ref)
    if ref.name in KEYCLOAK_NAMES:
        return keycloak_violations(ref)
    return generic_violations(ref)


# Text references in files other than the composition (whose `image:` is checked as rendered).
# Docker's tag characters, plus `$` and `{` so a tag taken from a variable is caught, not skipped.
_TAG = r"[\w.${}-]+"
_PREFIX = r"(?:docker\.io/library/|library/)?postgres"
TAGGED_OR_DIGEST = re.compile(
    r"(?<![\w./@:-])(?P<ref>" + _PREFIX + r"(?::" + _TAG + r")?(?:@[\w:]*)?)"
)
UNTAGGED_IMAGE_LINE = re.compile(
    r"^\s*(?:-\s*)?[\"']?image[\"']?\s*:\s*[\"']?(?P<ref>" + _PREFIX + r")[\"']?\s*(?:#.*)?$"
)
UNTAGGED_FROM_LINE = re.compile(
    r"^\s*FROM\s+(?:--\S+\s+)*(?P<ref>" + _PREFIX + r")(?:\s+AS\s+\S+)?\s*$", re.IGNORECASE
)
_KEYCLOAK = r"(?:quay\.io/|docker\.io/)?keycloak/keycloak"
KEYCLOAK_TAGGED = re.compile(r"(?<![\w./-])(?P<ref>" + _KEYCLOAK + r"(?::" + _TAG + r"|@[\w:]*)+)")
UNTAGGED_KEYCLOAK_LINE = re.compile(
    r"^\s*(?:(?:-\s*)?[\"']?image[\"']?\s*:\s*[\"']?|FROM\s+(?:--\S+\s+)*)(?P<ref>"
    + _KEYCLOAK
    + r")[\"']?(?:\s+AS\s+\S+)?\s*(?:#.*)?$",
    re.IGNORECASE,
)


def postgres_text_references(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        for pattern in (UNTAGGED_IMAGE_LINE, UNTAGGED_FROM_LINE):
            match = pattern.match(line)
            if match:
                found.append(match.group("ref"))
        for match in TAGGED_OR_DIGEST.finditer(line):
            ref = match.group("ref")
            after = line[match.end() : match.end() + 2]
            # `postgres:` as a YAML key, `postgres://` as a connection string: not image refs.
            if ref.endswith(("postgres", "postgresql")) or after.startswith("//"):
                continue
            if ref.split(":", 1)[-1].startswith("//"):
                continue
            found.append(ref)
    return found


def keycloak_text_references(text: str) -> list[str]:
    """Like ADR-0002-C12's rule: an untagged name counts only where an image is named."""
    found = []
    for line in text.splitlines():
        match = UNTAGGED_KEYCLOAK_LINE.match(line)
        if match:
            found.append(match.group("ref"))
        found += [m.group("ref") for m in KEYCLOAK_TAGGED.finditer(line)]
    return found
