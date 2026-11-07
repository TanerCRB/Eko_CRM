"""EKO-1-15 K-05 (ADR-0004-C31, second half): a published release never changes.

The second run is one K-04's gate admits in every other element (same tag form, `main`,
`TanerCRB`), so only the already-published refusal can stop it. "Published" is the release
composition artifact in the record; pushed images alone do not make a release.
"""

import json

import pytest

from tests.static.release_doubles import MAIN, ReachDouble, record
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


def test_eko115_k05_a_tag_whose_composition_exists_is_refused() -> None:
    decision = admission(tag_push("v1.2.0"), record("v1.2.0"), ReachDouble())
    assert not decision.admitted
    assert "already published" in decision.reason


def test_eko115_k05_contrast_images_without_a_composition_are_not_a_release() -> None:
    # The images of v1.2.0 were pushed by a run that failed before the composition (G-9 A): the
    # record holds no v1.2.0, so a re-run is admitted.
    decision = admission(tag_push("v1.2.0"), record("v1.1.0"), ReachDouble())
    assert decision.admitted, decision.reason


def test_eko115_k05_edge_a_tag_re_pushed_on_another_main_commit_is_refused_by_name() -> None:
    decision = admission(tag_push("v1.2.0", sha=MAIN), record("v1.2.0"), ReachDouble())
    assert not decision.admitted


def test_eko115_k05_edge_a_second_tag_on_the_same_commit_is_a_new_release() -> None:
    published = record("v1.2.0", commit=MAIN)
    assert admission(tag_push("v1.2.1", sha=MAIN), published, ReachDouble()).admitted
    assert published.release("v1.2.0").commit == MAIN


class Registry:
    """An OCI registry double: token, manifests and blobs, recording every write."""

    def __init__(self, manifests: dict[str, bytes] | None = None) -> None:
        self.manifests = dict(manifests or {})
        self.writes: list[str] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> Response:
        if "/token?" in url:
            return Response(200, {}, json.dumps({"token": "t"}).encode())
        if method in ("PUT", "POST"):
            self.writes.append(url)
            return Response(201 if method == "PUT" else 202, {"location": "/upload/1"}, b"")
        if "/manifests/" in url:
            tag = url.rsplit("/", 1)[-1]
            if tag in self.manifests:
                return Response(200, {}, self.manifests[tag])
            return Response(
                404, {}, json.dumps({"errors": [{"code": "MANIFEST_UNKNOWN"}]}).encode()
            )
        return Response(404, {}, b"")


def manifest() -> bytes:
    return json.dumps(
        {
            "mediaType": MANIFEST_TYPE,
            "artifactType": ARTIFACT_TYPE,
            "layers": [{"mediaType": COMPOSITION_TYPE, "digest": "sha256:" + "0" * 64}],
            "annotations": {"org.opencontainers.image.revision": MAIN},
        }
    ).encode()


def test_eko115_k05_publish_refuses_a_tag_the_record_holds_and_writes_nothing() -> None:
    registry = Registry({"v1.2.0": manifest()})
    with pytest.raises(CannotTell, match="already holds it"):
        GhcrRecord("token", registry).publish("v1.2.0", MAIN, "services: {}\n")
    assert registry.writes == []


def test_eko115_k05_contrast_publish_writes_a_tag_the_record_does_not_hold() -> None:
    registry = Registry()
    GhcrRecord("token", registry).publish("v1.2.0", MAIN, "services: {}\n")
    assert any(url.endswith("/manifests/v1.2.0") for url in registry.writes)
