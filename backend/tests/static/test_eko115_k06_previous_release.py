"""EKO-1-15 K-06: the API-compatibility step and C13's previous-release half read the newest
published release reachable from `main`, from the record, never from a repository file.

The record and the served document are stand-ins; reachability is decided by a real Git
repository in a temporary directory (cases 6).
"""

import copy
import io
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.static.release_doubles import (
    BRANCH,
    MAIN,
    ReachDouble,
    RecordDouble,
    backend_ref,
    record,
    release,
)
from tests.support import api_surface as api
from tests.support import openapi_compat as oc
from tests.support.releases import (
    ARTIFACT_TYPE,
    COMPOSITION_TYPE,
    CannotTell,
    GhcrRecord,
    GitReachability,
    Release,
    Response,
    c13_previous_backend,
    previous_release,
)

COMPARED = re.compile(r"compared \d+ operation")
Document = dict[str, Any]


def served_by(document: Document | None) -> Callable[[Release], Document]:
    def serve(found: Release) -> Document:
        if document is None:
            raise CannotTell(f"{found.tag}: backend did not answer")
        return copy.deepcopy(document)

    return serve


def run(
    rec: Any,
    reach: Any = None,
    document: Document | None = None,
    *argv: str,
) -> tuple[int, str]:
    out = io.StringIO()
    real = api.real_app().openapi()
    code = oc.main(
        ["--from-record", *argv],
        out,
        record=rec,
        reach=reach or ReachDouble(),
        served=served_by(real if document is None else document),
    )
    return code, out.getvalue()


# (1) no release ----------------------------------------------------------------------------


def test_eko115_k06_1_no_release_compares_nothing() -> None:
    code, output = run(record())
    assert code == 0 and "compared nothing" in output and not COMPARED.search(output), output
    assert c13_previous_backend(record(), ReachDouble(), None) is None


def test_eko115_k06_1_only_unreachable_releases_count_as_none() -> None:
    rec = record("v1.3.0", commit=BRANCH)
    code, output = run(rec)
    assert code == 0 and "compared nothing" in output, output
    assert c13_previous_backend(rec, ReachDouble(), None) is None


# (2) one release ---------------------------------------------------------------------------


def test_eko115_k06_2_one_release_reports_a_comparison() -> None:
    code, output = run(record("v1.2.0"))
    assert code == 0 and COMPARED.search(output) and "v1.2.0" in output, output
    assert c13_previous_backend(record("v1.2.0"), ReachDouble(), None) == backend_ref("v1.2.0")


def test_eko115_k06_2_a_removed_operation_fails_against_the_release() -> None:
    previous = api.real_app().openapi()
    previous["paths"]["/api/visits"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    code, output = run(record("v1.2.0"), None, previous)
    assert code == 1 and "GET /api/visits: operation removed" in output, output


def test_eko115_k06_2_the_release_being_built_is_excluded() -> None:
    code, output = run(record("v1.2.0"), None, None, "--exclude", "v1.2.0")
    assert code == 0 and "compared nothing" in output, output
    assert c13_previous_backend(record("v1.2.0"), ReachDouble(), "v1.2.0") is None


# (3) published but cannot be obtained ------------------------------------------------------


def _refused() -> RecordDouble:
    return RecordDouble(releases=record("v1.2.0").releases, refuse_listing=True)


def _missing() -> RecordDouble:
    return RecordDouble(releases=record("v1.2.0").releases, missing={"v1.2.0"})


@pytest.mark.parametrize("make", [_refused, _missing], ids=["listing-refused", "missing"])
def test_eko115_k06_3_unobtainable_release_exits_2(make: Callable[[], RecordDouble]) -> None:
    code, output = run(make())
    assert code == 2 and "compared nothing" not in output, output
    with pytest.raises(CannotTell):
        c13_previous_backend(make(), ReachDouble(), None)


def test_eko115_k06_3_backend_not_answering_exits_2() -> None:
    out = io.StringIO()
    code = oc.main(
        ["--from-record"], out, record=record("v1.2.0"), reach=ReachDouble(), served=served_by(None)
    )
    assert code == 2 and "compared nothing" not in out.getvalue(), out.getvalue()


def test_eko115_k06_3_backend_not_in_digest_form_is_cannot_tell() -> None:
    tagged = Release("v1.2.0", MAIN, "services:\n  backend:\n    image: x/backend:v1.2.0\n")
    with pytest.raises(CannotTell):
        c13_previous_backend(RecordDouble({"v1.2.0": tagged}), ReachDouble(), None)


def registry(status: int, body: bytes, link: str = "") -> Callable[..., Response]:
    def transport(method: str, url: str, headers: dict[str, str], data: bytes | None) -> Response:
        if "/token?" in url:
            return Response(200, {}, b'{"token": "t"}')
        return Response(status, {"link": link} if link else {}, body)

    return transport


@pytest.mark.parametrize("status", [401, 403, 500])
def test_eko115_k06_3_ghcr_listing_refused_is_cannot_tell(status: int) -> None:
    body = json.dumps({"errors": [{"code": "DENIED"}]}).encode()
    with pytest.raises(CannotTell):
        GhcrRecord("token", registry(status, body)).tags()


def test_eko115_k06_3_token_refused_is_cannot_tell() -> None:
    def transport(method: str, url: str, headers: dict[str, str], data: bytes | None) -> Response:
        return Response(403, {}, b"")

    with pytest.raises(CannotTell):
        GhcrRecord("token", transport).tags()


def test_eko115_k06_3_no_token_is_cannot_tell() -> None:
    with pytest.raises(CannotTell):
        GhcrRecord("")


def test_eko115_k06_1_ghcr_record_never_pushed_lists_nothing() -> None:
    body = json.dumps({"errors": [{"code": "NAME_UNKNOWN"}]}).encode()
    assert GhcrRecord("token", registry(404, body)).tags() == []


def test_eko115_k06_3_composition_not_matching_its_digest_is_cannot_tell() -> None:
    manifest = json.dumps(
        {
            "artifactType": ARTIFACT_TYPE,
            "layers": [{"mediaType": COMPOSITION_TYPE, "digest": "sha256:" + "0" * 64}],
            "annotations": {"org.opencontainers.image.revision": MAIN},
        }
    ).encode()

    def transport(method: str, url: str, headers: dict[str, str], data: bytes | None) -> Response:
        if "/token?" in url:
            return Response(200, {}, b'{"token": "t"}')
        if "/manifests/" in url:
            return Response(200, {}, manifest)
        return Response(200, {}, b"services: {}\n")

    with pytest.raises(CannotTell, match="does not match"):
        GhcrRecord("token", transport).release("v1.2.0")


def test_eko115_k06_edge_newest_release_beyond_the_first_page_is_found() -> None:
    pages = {
        "first": (
            json.dumps({"tags": ["v1.0.0", "v1.1.0"]}),
            '</v2/x/tags/list?last=v1.1.0>; rel="next"',
        ),
        "second": (json.dumps({"tags": ["v1.10.0"]}), ""),
    }

    def transport(method: str, url: str, headers: dict[str, str], data: bytes | None) -> Response:
        if "/token?" in url:
            return Response(200, {}, b'{"token": "t"}')
        body, link = pages["second" if "last=" in url else "first"]
        return Response(200, {"link": link} if link else {}, body.encode())

    assert GhcrRecord("token", transport).tags() == ["v1.0.0", "v1.1.0", "v1.10.0"]


# (4) a planted document or an edited fixture changes nothing --------------------------------


def test_eko115_k06_4_a_planted_document_is_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planted = api.real_app().openapi()
    planted["paths"]["/api/planted"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    for name in ("openapi.json", "previous.json", "openapi-previous.json"):
        (tmp_path / name).write_text(json.dumps(planted), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code, output = run(record("v1.2.0"))
    assert code == 0 and "/api/planted" not in output and COMPARED.search(output), output


def test_eko115_k06_4_from_record_refuses_a_document_from_a_file(tmp_path: Path) -> None:
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(api.real_app().openapi()), encoding="utf-8")
    with pytest.raises(SystemExit) as raised:
        run(record("v1.2.0"), None, None, "--previous", str(previous))
    assert raised.value.code == 2


# (5) ordering, the same in both consumers ---------------------------------------------------


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (("v1.9.0", "v1.10.0"), "v1.10.0"),
        (("v1.99.99", "v2.0.0"), "v2.0.0"),
        (("v1.2.0", "v1.3.0-rc1", "v01.4.0", "latest"), "v1.2.0"),
    ],
)
def test_eko115_k06_5_both_consumers_pick_the_same_release(
    tags: tuple[str, ...], expected: str
) -> None:
    rec = record(*tags)
    code, output = run(rec)
    assert code == 0 and f"previous release {expected}" in output, output
    assert c13_previous_backend(rec, ReachDouble(), None) == backend_ref(expected)


# (6) reachability from main, in a real repository --------------------------------------------


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "sandbox@example.com")
        self.git("config", "user.name", "sandbox")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(self, message: str) -> str:
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path: Path) -> tuple[Repo, str, str]:
    """`main` with one commit after the base; a PR branch with a commit not on main, checked out."""
    repo = Repo(tmp_path / "repo")
    on_main = repo.commit("base")
    repo.git("checkout", "-q", "-b", "pr")
    on_branch = repo.commit("branch")
    repo.git("checkout", "-q", "main")
    repo.commit("main moves on")
    repo.git("checkout", "-q", "pr")
    return repo, on_main, on_branch


def test_eko115_k06_6_a_release_off_main_is_skipped(history: tuple[Repo, str, str]) -> None:
    repo, on_main, on_branch = history
    rec = RecordDouble(
        {"v1.3.0": release("v1.3.0", on_branch), "v1.2.0": release("v1.2.0", on_main)}
    )
    reach = GitReachability(repo.root, "main")
    found = previous_release(rec, reach, None)
    assert found is not None and found.tag == "v1.2.0"
    assert c13_previous_backend(rec, reach, None) == backend_ref("v1.2.0")
    code, output = run(rec, reach)
    assert code == 0 and "previous release v1.2.0" in output, output


def test_eko115_k06_6_contrast_the_same_release_on_main_is_picked(
    history: tuple[Repo, str, str],
) -> None:
    repo, on_main, on_branch = history
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "--no-ff", "-m", "merge", "pr")
    rec = RecordDouble(
        {"v1.3.0": release("v1.3.0", on_branch), "v1.2.0": release("v1.2.0", on_main)}
    )
    found = previous_release(rec, GitReachability(repo.root, "main"), None)
    assert found is not None and found.tag == "v1.3.0"


@pytest.mark.parametrize("what", ["unknown-commit", "no-main-ref", "shallow"])
def test_eko115_k06_6_undeterminable_reachability_exits_2(
    history: tuple[Repo, str, str], tmp_path: Path, what: str
) -> None:
    repo, on_main, on_branch = history
    root, ref, commit = repo.root, "main", on_main
    if what == "unknown-commit":
        commit = "d" * 40
    elif what == "no-main-ref":
        ref = "origin/main"
    else:
        shallow = tmp_path / "shallow"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", "--branch", "main", root.as_uri(), str(shallow)],
            check=True,
            capture_output=True,
        )
        root, ref = shallow, "origin/main"
    rec = RecordDouble({"v1.2.0": release("v1.2.0", commit)})
    code, output = run(rec, GitReachability(root, ref))
    assert code == 2 and "compared nothing" not in output, output
    with pytest.raises(CannotTell):
        c13_previous_backend(rec, GitReachability(root, ref), None)


def test_eko115_k06_6_shallow_contrast_full_clone_decides(
    history: tuple[Repo, str, str], tmp_path: Path
) -> None:
    repo, on_main, _ = history
    full = tmp_path / "full"
    subprocess.run(
        ["git", "clone", "-q", "--branch", "main", repo.root.as_uri(), str(full)],
        check=True,
        capture_output=True,
    )
    assert GitReachability(full, "origin/main").reachable(on_main)


def test_eko115_k06_edge_the_record_holds_a_non_release_artifact() -> None:
    assert previous_release(record("rehearsal-1", "v1.2.0-rc1"), ReachDouble(), None) is None


def test_eko115_k06_edge_main_given_by_hex_string_must_be_full() -> None:
    with pytest.raises(CannotTell):
        GitReachability(Path("."), "main").reachable(MAIN[:12])
