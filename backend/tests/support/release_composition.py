"""The release composition: `compose.yaml` at the release tag with every shared-profile image in
digest form (ADR-0004 addendum 2026-11-04, *The release composition*; ADR-0004-C29).

    uv run python -m tests.support.release_composition render --tag T --digests FILE \
        --postgres sha256:... --out FILE
    uv run python -m tests.support.release_composition check --composition FILE

`render` edits the composition's text, so comments, anchors and every `${NAME:?…}` stay as
written; no environment value is substituted. Project images name
`ghcr.io/tanercrb/eko-crm/<name>:<tag>@<digest>` — the five the release run builds and pushes,
including the custom Keycloak image (EKO-1-26 route A, ADR-0004 addendum draft); its digest comes
from the run's own pushes, in the same `--digests` file as the other four. `postgres` keeps its
tag and gains the digest the release run's runtime tests pulled; `build:` (and the
`pull_policy: build` that goes with it) is removed from every shared-profile service.

Exit codes: 0 = written or the rules hold; 1 = a rule is broken; 2 = the command itself failed.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any, TextIO

import yaml

from tests.support.image_refs import DIGEST, parse
from tests.support.repo import REPO_ROOT

PROJECT_REGISTRY = "ghcr.io/tanercrb/eko-crm"
# EKO-1-26 (route A): the custom Keycloak image is the fifth project image — the release run
# builds it from `identity/`, checks and pushes it, and the composition names it by that digest.
PROJECT_IMAGES = ("backend", "frontend", "proxy", "backup", "keycloak")
ON_BACKEND_IMAGE = ("backend", "migrate", "worker")
THIRD_PARTY = ("postgres",)
SERVICE = re.compile(r"^  (?P<name>[a-z][a-z0-9_-]*):\s*$")
KEY = re.compile(r"^    (?P<key>[a-z_]+):(?P<rest>.*)$")
IMAGE_VALUE = re.compile(r"^(?P<anchor>\s*&\S+)?\s*(?P<ref>\S.*?)\s*$")
RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
REQUIRED = re.compile(r"\$\{[A-Z][A-Z0-9_]*:\?[^}]*\}")
FROM = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(?P<ref>\S+)", re.IGNORECASE | re.MULTILINE)
# The one required variable a digest replaces: the local backend tag of the repository build.
REPLACED_VARIABLES = {"${BACKEND_IMAGE_TAG:?BACKEND_IMAGE_TAG is required}"}
DOCKERFILES = ("proxy/Dockerfile",)


def _check_digest(name: str, digest: str) -> str:
    if not DIGEST.fullmatch(digest):
        raise ValueError(f"{name}: {digest!r} is not sha256 with 64 lower-case hex digits")
    return digest


def _image_for(service: str, current: str | None, tag: str, digests: dict[str, str]) -> str:
    if service in ON_BACKEND_IMAGE or service in PROJECT_IMAGES:
        name = "backend" if service in ON_BACKEND_IMAGE else service
        return f"{PROJECT_REGISTRY}/{name}:{tag}@{_check_digest(name, digests.get(name, ''))}"
    if service in THIRD_PARTY and current is not None:
        return f"{current.split('@')[0]}@{_check_digest(service, digests.get(service, ''))}"
    raise ValueError(f"{service}: no release image is defined for this service")


def render(compose: str, tag: str, digests: dict[str, str]) -> str:
    """The release composition of `tag`; `digests` maps the five project images and postgres
    to the digest the release names (EKO-1-26: keycloak among the project images)."""
    if not RELEASE_TAG.fullmatch(tag):
        raise ValueError(f"{tag!r} is not a release tag")
    shared = {
        name
        for name, service in (yaml.safe_load(compose).get("services") or {}).items()
        if not service.get("profiles")
    }
    lines = compose.replace("\r\n", "\n").split("\n")
    out: list[str] = [
        f"# Release composition of {tag} (ADR-0004-C29), rendered by the release run."
    ]
    service: str | None = None
    in_services = skipping = False
    has_image: dict[str, bool] = {}
    for line in lines:
        if line and not line.startswith(" ") and not line.startswith("#"):
            in_services, service, skipping = line.startswith("services:"), None, False
        match = SERVICE.match(line) if in_services else None
        if match:
            service, skipping = match.group("name"), False
        if service is None or service not in shared or not in_services:
            out.append(line)
            continue
        if skipping:
            if line.startswith("      ") or not line.strip():
                continue
            skipping = False
        key = KEY.match(line)
        if key and key.group("key") == "build":
            skipping = True
            if not has_image.get(service):
                out.append(f"    image: {_image_for(service, None, tag, digests)}")
                has_image[service] = True
            continue
        if key and key.group("key") == "pull_policy" and key.group("rest").strip() == "build":
            continue
        if key and key.group("key") == "image":
            value = IMAGE_VALUE.match(key.group("rest"))
            if value is None:
                raise ValueError(f"{service}: image line not understood")
            anchor = (value.group("anchor") or "").strip()
            image = _image_for(service, value.group("ref"), tag, digests)
            out.append(f"    image: {anchor + ' ' if anchor else ''}{image}")
            has_image[service] = True
            continue
        out.append(line)
    missing = sorted(shared - {s for s, done in has_image.items() if done})
    if missing:
        raise ValueError(f"no release image rendered for {', '.join(missing)}")
    return "\n".join(out)


# ADR-0004-C29 ----------------------------------------------------------------------------------


def digest_violations(reference: str) -> list[str]:
    """A reference in digest form: `<name>[:<tag>]@sha256:<64 lower-case hex>`."""
    ref = parse(reference.strip())
    if ref.digest is None:
        return [f"{reference!r} carries no digest"]
    if not DIGEST.fullmatch(ref.digest):
        return [f"{reference!r}: digest is not sha256 with 64 lower-case hex digits"]
    return []


def dockerfile_violations(path: str, text: str) -> list[str]:
    found = FROM.findall(text)
    if not found:
        return [f"{path}: no FROM"]
    return [f"{path}: FROM {ref}: {p}" for ref in found for p in digest_violations(ref)]


def c29_violations(source: dict[str, Any], proxy_dockerfile: str) -> list[str]:
    """Every shared-profile service runs an image by digest and none builds; `proxy`'s base
    carries a digest."""
    problems = []
    for name, service in (source.get("services") or {}).items():
        if service.get("profiles"):
            continue
        if "build" in service:
            problems.append(f"{name}: has build (an image built on the server)")
        if "image" not in service:
            problems.append(f"{name}: has no image")
            continue
        problems += [f"{name}: {p}" for p in digest_violations(str(service["image"]))]
    return problems + dockerfile_violations("proxy/Dockerfile", proxy_dockerfile)


def variable_violations(repository: str, release: str) -> list[str]:
    """Every required variable of the repository composition stays, as written, in the release
    composition, but the backend tag its digest replaces; none is added."""
    before = set(REQUIRED.findall(repository)) - REPLACED_VARIABLES
    after = set(REQUIRED.findall(release))
    return [f"required variable {v} is gone" for v in sorted(before - after)] + [
        f"required variable {v} is new" for v in sorted(after - before)
    ]


# Command line ------------------------------------------------------------------------------------


def report(out: TextIO, line: str) -> None:
    """The command's result, one line each: the CLI's output, not logging."""
    out.write(line + "\n")


def read_digests(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").split() if line)
    return {name: value for name, value in pairs}


def main(argv: list[str], out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.support.release_composition")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("render")
    make.add_argument("--tag", required=True)
    make.add_argument("--digests", required=True, help="name=sha256:... lines of the pushes")
    make.add_argument("--postgres", required=True)
    make.add_argument("--out", required=True)
    check = commands.add_parser("check")
    check.add_argument("--composition", required=True)
    args = parser.parse_args(argv)
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    try:
        if args.command == "render":
            # EKO-1-26 K-03: the custom keycloak image is a pushed project image; its digest
            # arrives in the pushes' file, so the command names no `--keycloak` reference.
            digests = read_digests(Path(args.digests))
            digests.update(postgres=args.postgres)
            Path(args.out).write_text(render(compose, args.tag, digests), encoding="utf-8")
            report(out, f"release-composition: rendered {args.tag}")
            return 0
        text = Path(args.composition).read_text(encoding="utf-8")
        dockerfile = (REPO_ROOT / "proxy" / "Dockerfile").read_text(encoding="utf-8")
        problems = c29_violations(yaml.safe_load(text), dockerfile)
        problems += variable_violations(compose, text)
    except (OSError, ValueError, yaml.YAMLError) as error:
        report(out, f"release-composition: the command itself failed: {error}")
        return 2
    for problem in problems:
        report(out, f"VIOLATION: {problem}")
    report(out, f"release-composition: {len(problems)} violation(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
