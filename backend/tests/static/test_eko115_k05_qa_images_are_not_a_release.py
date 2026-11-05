"""EKO-1-15 K-05 fixture (b), added by QA, at the registry: images pushed under a tag by a run
that failed before the composition (G-9 A) are not a release; only the release-composition
artifact in `ghcr.io/tanercrb/eko-crm/release` is.

The admission fixtures elsewhere use a record stand-in that has no images at all, so "images
exist" and "the composition exists" are never told apart there. This registry stand-in keeps
each repository's manifests apart, as GHCR does.
"""

import json
import re
import urllib.parse

import pytest

from tests.static.release_doubles import MAIN, ReachDouble
from tests.static.test_eko115_k04_registry_write import tag_push
from tests.support.releases import (
    ARTIFACT_TYPE,
    COMPOSITION_TYPE,
    MANIFEST_TYPE,
    CannotTell,
    GhcrRecord,
    Response,
    admission,
)

RELEASE_REPO = "tanercrb/eko-crm/release"
BACKEND_REPO = "tanercrb/eko-crm/backend"
TAGS = re.compile(r"/v2/(?P<repo>.+)/tags/list")
MANIFEST = re.compile(r"/v2/(?P<repo>.+)/manifests/(?P<ref>[^/]+)")
UPLOAD = re.compile(r"/v2/(?P<repo>.+)/blobs/uploads/.*")
BLOB = re.compile(r"/v2/(?P<repo>.+)/blobs/(?P<digest>[^/]+)")


def unknown(code: str) -> bytes:
    return json.dumps({"errors": [{"code": code}]}).encode()


class Registry:
    """Manifests by (repository, tag); every write recorded as (method, repository, path)."""

    def __init__(self, manifests: dict[tuple[str, str], bytes]) -> None:
        self.manifests = dict(manifests)
        self.writes: list[tuple[str, str, str]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> Response:
        path = urllib.parse.urlsplit(url).path
        if path == "/token":
            return Response(200, {}, b'{"token": "t"}')
        if found := TAGS.fullmatch(path):
            tags = sorted(t for r, t in self.manifests if r == found["repo"])
            if not tags:
                return Response(404, {}, unknown("NAME_UNKNOWN"))
            return Response(200, {}, json.dumps({"tags": tags}).encode())
        if found := UPLOAD.fullmatch(path):
            self.writes.append((method, found["repo"], path))
            if method == "POST":
                return Response(202, {"location": f"/v2/{found['repo']}/blobs/uploads/1"}, b"")
            return Response(201, {}, b"")
        if found := MANIFEST.fullmatch(path):
            key = (found["repo"], found["ref"])
            if method == "PUT":
                self.writes.append((method, found["repo"], path))
                self.manifests[key] = body or b""
                return Response(201, {}, b"")
            if key in self.manifests:
                return Response(200, {}, self.manifests[key])
            return Response(404, {}, unknown("MANIFEST_UNKNOWN"))
        if BLOB.fullmatch(path):
            return Response(404, {}, b"")
        raise AssertionError(f"unexpected call {method} {path}")


def image_manifest() -> bytes:
    return json.dumps(
        {
            "mediaType": MANIFEST_TYPE,
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json"},
            "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"}],
        }
    ).encode()


def release_manifest() -> bytes:
    return json.dumps(
        {
            "mediaType": MANIFEST_TYPE,
            "artifactType": ARTIFACT_TYPE,
            "layers": [{"mediaType": COMPOSITION_TYPE, "digest": "sha256:" + "0" * 64}],
            "annotations": {"org.opencontainers.image.revision": MAIN},
        }
    ).encode()


IMAGES_ONLY = {(BACKEND_REPO, "v1.2.0"): image_manifest()}
PUBLISHED = {**IMAGES_ONLY, (RELEASE_REPO, "v1.2.0"): release_manifest()}


def test_eko115_k05_qa_pushed_images_alone_are_not_a_release() -> None:
    registry = Registry(IMAGES_ONLY)
    assert GhcrRecord("token", registry).tags() == []
    assert admission(tag_push("v1.2.0"), GhcrRecord("token", registry), ReachDouble()).admitted
    GhcrRecord("token", registry).publish("v1.2.0", MAIN, "services: {}\n")
    assert ("PUT", RELEASE_REPO, f"/v2/{RELEASE_REPO}/manifests/v1.2.0") in registry.writes
    assert [w for w in registry.writes if w[1] != RELEASE_REPO] == []
    assert registry.manifests[(BACKEND_REPO, "v1.2.0")] == image_manifest()


def test_eko115_k05_qa_contrast_the_composition_artifact_makes_the_release() -> None:
    registry = Registry(PUBLISHED)
    assert GhcrRecord("token", registry).tags() == ["v1.2.0"]
    decision = admission(tag_push("v1.2.0"), GhcrRecord("token", registry), ReachDouble())
    assert not decision.admitted and "already published" in decision.reason
    with pytest.raises(CannotTell, match="already holds it"):
        GhcrRecord("token", registry).publish("v1.2.0", MAIN, "services: {}\n")
    assert registry.writes == []
