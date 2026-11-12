"""Release tags, the record of published releases, the release run's admission and the previous
release (ADR-0004 addendum 2026-11-04; EKO-1-15, #56).

    uv run python -m tests.support.releases admit                 # in a release run
    uv run python -m tests.support.releases previous [--exclude TAG]
    uv run python -m tests.support.releases published TAG         # exit 0 only if not published
    uv run python -m tests.support.releases publish --tag T --commit C --composition FILE
    uv run python -m tests.support.releases tag-commit --tag T --commit C   # exit 0: T names C

The record is the OCI artifact repository `ghcr.io/tanercrb/eko-crm/release`: one artifact per
release tag, holding the release composition and the tagged commit. A tag the record holds is a
published release; images alone never make one. `main` is `origin/main` in the checkout (override:
RELEASE_MAIN_REF); the record token is RELEASE_RECORD_TOKEN (the run's own GITHUB_TOKEN).

Exit codes: 0 = admitted, or decided; 1 = refused; 2 = cannot tell (the check itself failed,
never read as "no release").
"""

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

import yaml

RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT = re.compile(r"[0-9a-f]{40}")
# C-2: the one account that may publish; an agent session never pushes a release tag (#83).
PERMITTED_ACCOUNTS = frozenset({"TanerCRB"})
REGISTRY = "ghcr.io"
NAMESPACE = "tanercrb/eko-crm"
RECORD_REPOSITORY = f"{NAMESPACE}/release"
PROJECT_IMAGES = ("backend", "frontend", "backup", "proxy")

MANIFEST_TYPE = "application/vnd.oci.image.manifest.v1+json"
ARTIFACT_TYPE = "application/vnd.eko-crm.release.v1"
COMPOSITION_TYPE = "application/vnd.eko-crm.release-composition.v1+yaml"
EMPTY_TYPE = "application/vnd.oci.empty.v1+json"
EMPTY_BLOB = b"{}"
REVISION = "org.opencontainers.image.revision"
VERSION = "org.opencontainers.image.version"
PAGE_SIZE = 100
MAX_PAGES = 1000


class CannotTell(Exception):
    """The record, a release in it, or reachability from `main` could not be determined."""


def version(tag: str) -> tuple[int, int, int] | None:
    match = RELEASE_TAG.fullmatch(tag)
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


@dataclass(frozen=True)
class Release:
    tag: str
    commit: str
    composition: str


class Record(Protocol):
    def tags(self) -> list[str]: ...

    def release(self, tag: str) -> Release: ...


class Reachability(Protocol):
    def reachable(self, commit: str) -> bool: ...


def previous_release(record: Record, reach: Reachability, exclude: str | None) -> Release | None:
    """The highest release in numeric tag order, other than `exclude`, whose tagged commit is
    reachable from `main` now (G-1 A, G-6 A+); None when the record holds no such release."""
    candidates = [tag for tag in record.tags() if version(tag) is not None and tag != exclude]
    for tag in sorted(candidates, key=lambda t: version(t) or (0, 0, 0), reverse=True):
        found = record.release(tag)
        if found.tag != tag or not COMMIT.fullmatch(found.commit):
            raise CannotTell(f"{tag}: the record entry names no tagged commit")
        if reach.reachable(found.commit):
            return found
    return None


DIGEST_REFERENCE = re.compile(r"[a-z0-9./:_-]+@sha256:[0-9a-f]{64}")


def backend_reference(found: Release) -> str:
    """The backend image of a release, by digest, as its release composition names it."""
    try:
        services = yaml.safe_load(found.composition)["services"]
        image = str(services["backend"]["image"])
    except (yaml.YAMLError, KeyError, TypeError):
        raise CannotTell(f"{found.tag}: the release composition names no backend image") from None
    if not DIGEST_REFERENCE.fullmatch(image):
        raise CannotTell(f"{found.tag}: the backend image is not named by digest")
    return image


def c13_previous_backend(record: Record, reach: Reachability, exclude: str | None) -> str | None:
    """ADR-0004-C13's previous-release half: the previous release's backend image by digest, or
    None while no release is published (the half then reports no pass)."""
    found = previous_release(record, reach, exclude)
    return None if found is None else backend_reference(found)


@dataclass(frozen=True)
class Event:
    """The facts of a workflow run the admission decides on, as GitHub reports them."""

    name: str
    ref: str
    sha: str
    actor: str
    triggering_actor: str


@dataclass(frozen=True)
class Decision:
    admitted: bool
    reason: str
    tag: str = ""


def admission(event: Event, record: Record, reach: Reachability) -> Decision:
    """ADR-0004-C30, C31: may this run publish? Raises CannotTell when it cannot decide."""
    if event.name != "push" or not event.ref.startswith("refs/tags/"):
        return Decision(False, f"event {event.name} on {event.ref} is not a tag push")
    tag = event.ref.removeprefix("refs/tags/")
    if version(tag) is None:
        return Decision(False, f"{tag} is not a release tag v<major>.<minor>.<patch>")
    for role, account in (("pushed", event.actor), ("started", event.triggering_actor)):
        if account not in PERMITTED_ACCOUNTS:
            return Decision(False, f"{tag}: {role} by an account that may not publish")
    if not reach.reachable(event.sha):
        return Decision(False, f"{tag}: the tagged commit is not on main")
    if tag in record.tags():
        return Decision(False, f"{tag}: already published; a published release never changes")
    previous = previous_release(record, reach, exclude=tag)
    if previous is not None and (version(previous.tag) or (0, 0, 0)) > (version(tag) or (0, 0, 0)):
        return Decision(False, f"{tag}: lower than the published release {previous.tag}")
    return Decision(True, f"{tag}: admitted", tag)


# Reachability from main, in a Git checkout ----------------------------------------------------


@dataclass(frozen=True)
class GitReachability:
    checkout: Path
    main_ref: str = "origin/main"

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.checkout, capture_output=True, text=True, check=False
        )

    def reachable(self, commit: str) -> bool:
        if not COMMIT.fullmatch(commit):
            raise CannotTell(f"{commit!r}: not a full commit name")
        shallow = self._git("rev-parse", "--is-shallow-repository")
        if shallow.returncode != 0 or shallow.stdout.strip() != "false":
            raise CannotTell("the checkout's history is shallow or unreadable")
        if self._git("rev-parse", "--verify", "--quiet", f"{self.main_ref}^{{commit}}").returncode:
            raise CannotTell(f"{self.main_ref} is not in the checkout")
        if self._git("cat-file", "-e", f"{commit}^{{commit}}").returncode:
            raise CannotTell(f"{commit}: not in the checkout's history")
        code = self._git("merge-base", "--is-ancestor", commit, self.main_ref).returncode
        if code not in (0, 1):
            raise CannotTell(f"{commit}: git merge-base exited {code}")
        return code == 0


# The record in GHCR, over the OCI distribution API -------------------------------------------


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


Transport = Callable[[str, str, dict[str, str], bytes | None], Response]


REDIRECTS = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 5


def https_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Response:
    """HTTPS only. A redirect (a blob's pre-signed storage URL) is followed without the registry
    token; errors name the host only, never a URL that may carry a signature."""
    for _ in range(MAX_REDIRECTS + 1):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise CannotTell("the record is reached over HTTPS only")
        connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=60)
        try:
            target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            connection.request(method, target, body=body, headers=headers)
            answer = connection.getresponse()
            data = answer.read()
            received = {name.lower(): value for name, value in answer.getheaders()}
        except (OSError, http.client.HTTPException) as error:
            raise CannotTell(f"{method} {parts.hostname}: {type(error).__name__}") from None
        finally:
            connection.close()
        if answer.status in REDIRECTS and "location" in received and method in ("GET", "HEAD"):
            url = urllib.parse.urljoin(url, received["location"])
            headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
            continue
        return Response(answer.status, received, data)
    raise CannotTell(f"{method}: more than {MAX_REDIRECTS} redirects")


def _error_codes(response: Response) -> set[str]:
    try:
        errors = json.loads(response.body or b"{}").get("errors") or []
    except (ValueError, AttributeError):
        return set()
    return {str(e.get("code")) for e in errors if isinstance(e, dict)}


NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')


class GhcrRecord:
    def __init__(
        self,
        token: str,
        transport: Transport = https_transport,
        repository: str = RECORD_REPOSITORY,
        registry: str = REGISTRY,
    ) -> None:
        if not token:
            raise CannotTell("no token to read the release record")
        self._token = token
        self._transport = transport
        self.repository = repository
        self.base = f"https://{registry}"
        self._bearers: dict[str, str] = {}

    def _bearer(self, actions: str) -> str:
        if actions not in self._bearers:
            scope = f"repository:{self.repository}:{actions}"
            query = urllib.parse.urlencode({"service": REGISTRY, "scope": scope})
            basic = base64.b64encode(f"token:{self._token}".encode()).decode()
            answer = self._transport(
                "GET", f"{self.base}/token?{query}", {"Authorization": f"Basic {basic}"}, None
            )
            if answer.status != 200:
                raise CannotTell(f"registry token refused ({answer.status})")
            try:
                self._bearers[actions] = str(json.loads(answer.body)["token"])
            except (ValueError, KeyError, TypeError):
                raise CannotTell("registry token answer unreadable") from None
        return self._bearers[actions]

    def _call(
        self,
        method: str,
        url: str,
        actions: str = "pull",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        if url.startswith("/"):
            url = self.base + url
        auth = {"Authorization": f"Bearer {self._bearer(actions)}", **(headers or {})}
        return self._transport(method, url, auth, body)

    def tags(self) -> list[str]:
        found: list[str] = []
        url: str | None = f"/v2/{self.repository}/tags/list?n={PAGE_SIZE}"
        for _ in range(MAX_PAGES):
            if url is None:
                return found
            answer = self._call("GET", url)
            if answer.status == 404 and _error_codes(answer) == {"NAME_UNKNOWN"}:
                # No artifact was ever pushed: the record exists by definition and lists nothing.
                return []
            if answer.status != 200:
                raise CannotTell(f"the record listing was refused ({answer.status})")
            try:
                found += [str(t) for t in json.loads(answer.body).get("tags") or []]
            except (ValueError, AttributeError):
                raise CannotTell("the record listing is unreadable") from None
            link = NEXT_LINK.search(answer.headers.get("link", ""))
            url = urllib.parse.urljoin(self.base, link.group(1)) if link else None
        raise CannotTell("the record listing does not end")

    def manifest(self, tag: str) -> Response:
        return self._call(
            "GET", f"/v2/{self.repository}/manifests/{tag}", headers={"Accept": MANIFEST_TYPE}
        )

    def release(self, tag: str) -> Release:
        answer = self.manifest(tag)
        if answer.status != 200:
            raise CannotTell(f"{tag}: release manifest cannot be obtained ({answer.status})")
        try:
            manifest = json.loads(answer.body)
            commit = str(manifest["annotations"][REVISION])
            [layer] = [x for x in manifest["layers"] if x.get("mediaType") == COMPOSITION_TYPE]
            digest = str(layer["digest"])
        except (ValueError, KeyError, TypeError):
            raise CannotTell(f"{tag}: not a release artifact") from None
        if manifest.get("artifactType") != ARTIFACT_TYPE:
            raise CannotTell(f"{tag}: not a release artifact")
        blob = self._call("GET", f"/v2/{self.repository}/blobs/{digest}")
        if blob.status != 200:
            raise CannotTell(f"{tag}: release composition cannot be obtained ({blob.status})")
        if "sha256:" + hashlib.sha256(blob.body).hexdigest() != digest:
            raise CannotTell(f"{tag}: release composition does not match its digest")
        try:
            composition = blob.body.decode("utf-8")
        except UnicodeDecodeError:
            raise CannotTell(f"{tag}: release composition is not text") from None
        return Release(tag=tag, commit=commit, composition=composition)

    def _upload(self, blob: bytes) -> str:
        digest = "sha256:" + hashlib.sha256(blob).hexdigest()
        if self._call("HEAD", f"/v2/{self.repository}/blobs/{digest}", "pull,push").status == 200:
            return digest
        started = self._call("POST", f"/v2/{self.repository}/blobs/uploads/", "pull,push")
        location = started.headers.get("location")
        if started.status != 202 or not location:
            raise CannotTell(f"blob upload refused ({started.status})")
        separator = "&" if "?" in location else "?"
        target = urllib.parse.urljoin(self.base, location) + f"{separator}digest={digest}"
        done = self._call(
            "PUT", target, "pull,push", {"Content-Type": "application/octet-stream"}, blob
        )
        if done.status != 201:
            raise CannotTell(f"blob upload failed ({done.status})")
        return digest

    def publish(self, tag: str, commit: str, composition: str) -> str:
        """Push the release artifact under `tag`; refuses a tag the record already holds."""
        if version(tag) is None or not COMMIT.fullmatch(commit):
            raise CannotTell(f"{tag} at {commit!r}: not a release tag and a full commit")
        existing = self.manifest(tag)
        if existing.status != 404:
            raise CannotTell(
                f"{tag}: the record already holds it or cannot tell ({existing.status})"
            )
        content = composition.encode("utf-8")
        manifest = {
            "schemaVersion": 2,
            "mediaType": MANIFEST_TYPE,
            "artifactType": ARTIFACT_TYPE,
            "config": {"mediaType": EMPTY_TYPE, "digest": self._upload(EMPTY_BLOB), "size": 2},
            "layers": [
                {
                    "mediaType": COMPOSITION_TYPE,
                    "digest": self._upload(content),
                    "size": len(content),
                    "annotations": {"org.opencontainers.image.title": "compose.release.yaml"},
                }
            ],
            "annotations": {REVISION: commit, VERSION: tag},
        }
        body = json.dumps(manifest, sort_keys=True).encode("utf-8")
        put = self._call(
            "PUT",
            f"/v2/{self.repository}/manifests/{tag}",
            "pull,push",
            {"Content-Type": MANIFEST_TYPE},
            body,
        )
        if put.status != 201:
            raise CannotTell(f"{tag}: release manifest push failed ({put.status})")
        return "sha256:" + hashlib.sha256(body).hexdigest()


# The tag in the repository, over the GitHub REST API -------------------------------------------

GITHUB_API = "https://api.github.com"
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# An annotated tag may point at another tag object; a chain this long is not a release tag.
MAX_TAG_OBJECTS = 5


class GitHubTags:
    """What a tag names in the repository now: a partial re-run keeps the commit its first
    attempt was started on (GITHUB_SHA), while the tag may since name another commit or none."""

    def __init__(self, token: str, repository: str, transport: Transport = https_transport) -> None:
        self._token = token
        self.repository = repository
        self._transport = transport

    def _object(self, path: str, tag: str) -> dict[str, str] | None:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "eko-crm-release-run",
        }
        answer = self._transport("GET", GITHUB_API + path, headers, None)
        if answer.status == 404:
            return None
        if answer.status != 200:
            raise CannotTell(f"{tag}: the tag cannot be read ({answer.status})")
        try:
            found = json.loads(answer.body)["object"]
            return {"type": str(found["type"]), "sha": str(found["sha"])}
        except (ValueError, KeyError, TypeError):
            raise CannotTell(f"{tag}: the tag answer is unreadable") from None

    def commit_of(self, tag: str) -> str | None:
        """The commit `tag` names, or None when the repository holds no such tag."""
        if not self._token or not REPOSITORY.fullmatch(self.repository):
            raise CannotTell("no token or repository to read the tag")
        if version(tag) is None:
            raise CannotTell(f"{tag}: not a release tag")
        found = self._object(f"/repos/{self.repository}/git/ref/tags/{tag}", tag)
        for _ in range(MAX_TAG_OBJECTS):
            if found is None:
                return None
            if not COMMIT.fullmatch(found["sha"]):
                raise CannotTell(f"{tag}: the tag names no full object name")
            if found["type"] == "commit":
                return found["sha"]
            if found["type"] != "tag":
                raise CannotTell(f"{tag}: the tag names a {found['type']}, not a commit")
            found = self._object(f"/repos/{self.repository}/git/tags/{found['sha']}", tag)
            if found is None:
                raise CannotTell(f"{tag}: its tag object cannot be obtained")
        raise CannotTell(f"{tag}: more than {MAX_TAG_OBJECTS} tag objects")


# Command line ---------------------------------------------------------------------------------


def report(out: TextIO, line: str) -> None:
    """The command's result, one line each: the CLI's output, not logging."""
    out.write(line + "\n")


def record_from_environment() -> GhcrRecord:
    return GhcrRecord(os.environ.get("RELEASE_RECORD_TOKEN", ""))


def reach_from_environment() -> GitReachability:
    return GitReachability(Path.cwd(), os.environ.get("RELEASE_MAIN_REF") or "origin/main")


def event_from_environment() -> Event:
    return Event(
        name=os.environ.get("GITHUB_EVENT_NAME", ""),
        ref=os.environ.get("GITHUB_REF", ""),
        sha=os.environ.get("GITHUB_SHA", ""),
        actor=os.environ.get("GITHUB_ACTOR", ""),
        triggering_actor=os.environ.get("GITHUB_TRIGGERING_ACTOR", ""),
    )


def tags_from_environment() -> GitHubTags:
    return GitHubTags(
        os.environ.get("RELEASE_REPO_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    )


def main(
    argv: list[str],
    out: TextIO = sys.stdout,
    record: Record | None = None,
    reach: Reachability | None = None,
    tags: GitHubTags | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.support.releases")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("admit")
    tag_commit = commands.add_parser("tag-commit")
    tag_commit.add_argument("--tag", required=True)
    tag_commit.add_argument("--commit", required=True)
    previous = commands.add_parser("previous")
    previous.add_argument("--exclude")
    publish = commands.add_parser("publish")
    publish.add_argument("--tag", required=True)
    publish.add_argument("--commit", required=True)
    publish.add_argument("--composition", required=True)
    args = parser.parse_args(argv)
    prefix = f"releases {args.command}:"
    try:
        if args.command == "publish":
            text = Path(args.composition).read_text(encoding="utf-8")
            digest = record_from_environment().publish(args.tag, args.commit, text)
            report(out, f"{prefix} published {args.tag} as {digest}")
            return 0
        if args.command == "tag-commit":
            named = (tags or tags_from_environment()).commit_of(args.tag)
            if named != args.commit:
                report(out, f"{prefix} {args.tag} no longer names {args.commit}")
                return 1
            report(out, f"{prefix} {args.tag} names {args.commit}")
            return 0
        record = record or record_from_environment()
        reach = reach or reach_from_environment()
        if args.command == "admit":
            decision = admission(event_from_environment(), record, reach)
            report(out, f"{prefix} {decision.reason}")
            if decision.admitted:
                report(out, f"tag={decision.tag}")
            return 0 if decision.admitted else 1
        found = previous_release(record, reach, args.exclude)
        if found is None:
            report(out, f"{prefix} no published release is reachable from main")
        else:
            report(out, f"{prefix} {found.tag} at {found.commit}")
        return 0
    except (CannotTell, OSError) as error:
        report(out, f"{prefix} the check itself failed: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
