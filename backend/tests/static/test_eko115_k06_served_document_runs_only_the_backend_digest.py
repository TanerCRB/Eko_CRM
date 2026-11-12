"""EKO-1-15 K-06, exception EKO-1-15/security-1 narrowing (Security Auditor B-01) and Reviewer R-03:
the API-compatibility step takes only the backend image digest from a record entry and runs it
under the head's own composition. A record entry's services, volumes, mounts and depends_on never
reach `docker compose`; the synthetic environment is the head's, so a variable only the previous
release's composition requires does not stop the step.

`docker compose` is a stand-in that records every call and the files it was given.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.static.release_doubles import MAIN_OLDER, ReachDouble, RecordDouble
from tests.static.test_eko115_k06_c13_override_runs_the_given_image import lab as c13_lab
from tests.static.test_eko115_k06_c13_override_runs_the_given_image import read_override
from tests.support import release_backend
from tests.support.releases import CannotTell, Release, c13_previous_backend
from tests.support.repo import REPO_ROOT

DIGEST = "ghcr.io/tanercrb/eko-crm/backend:v1.2.0@sha256:" + "1" * 64
OTHER_DIGEST = "ghcr.io/tanercrb/eko-crm/backend:v1.1.0@sha256:" + "2" * 64
DOCUMENT = {"openapi": "3.1.0", "paths": {}}
PLANTED = "planted-by-a-record-entry"


class ComposeDouble:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.files: dict[str, str] = {}

    def __call__(
        self, base: list[str], *args: str, timeout: int = 300
    ) -> subprocess.CompletedProcess[str]:
        command = [*base, *args]
        self.calls.append(command)
        for index, part in enumerate(command):
            if part == "-f":
                path = Path(command[index + 1])
                self.files[str(path)] = path.read_text(encoding="utf-8")
        out = json.dumps(DOCUMENT) if "exec" in args else ""
        return subprocess.CompletedProcess(command, 0, out, "")


def composition(backend: str, extra: str = "") -> str:
    return (
        "services:\n"
        "  backend:\n"
        f"    image: {backend}\n"
        "    volumes: ['/:/host']\n"
        f"    depends_on: [{PLANTED}]\n"
        "    environment:\n"
        "      APP_HOST: ${APP_HOST:?required}\n"
        f"  {PLANTED}:\n"
        "    image: docker.io/library/alpine:3\n"
        "    volumes: ['/var/run/docker.sock:/var/run/docker.sock', '/:/host']\n"
        f"{extra}"
    )


def release(backend: str = DIGEST, extra: str = "") -> Release:
    return Release(tag="v1.2.0", commit="a" * 40, composition=composition(backend, extra))


def serve(found: Release) -> tuple[Any, ComposeDouble]:
    double = ComposeDouble()
    return release_backend.served_document(found, compose=double), double


def overrides(double: ComposeDouble) -> list[dict[str, Any]]:
    head = str(REPO_ROOT / "compose.yaml")
    return [read_override(text) for p, text in double.files.items() if p != head]


def test_eko115_k06_a_record_composition_with_a_planted_service_is_not_run() -> None:
    document, double = serve(release())
    assert document == DOCUMENT
    assert double.files, "docker compose was given no file"
    assert str(REPO_ROOT / "compose.yaml") in double.files
    assert all(PLANTED not in text and "/host" not in text for text in double.files.values())
    assert all(PLANTED not in " ".join(call) for call in double.calls)
    [override] = overrides(double)
    assert set(override["services"]) == {"backend", "migrate"}
    for service in override["services"].values():
        assert set(service) <= {"image", "pull_policy", "build"}
        assert service["image"] == DIGEST
    assert override["services"]["backend"]["build"] == "!reset"
    up = [call for call in double.calls if "up" in call]
    assert len(up) == 1 and up[0][-1] == "backend", up


def test_eko115_k06_contrast_the_backend_run_is_the_record_entrys_digest() -> None:
    _, double = serve(release(OTHER_DIGEST))
    [override] = overrides(double)
    assert {s["image"] for s in override["services"].values()} == {OTHER_DIGEST}


def test_eko115_k06_a_record_backend_not_named_by_digest_is_not_run() -> None:
    double = ComposeDouble()
    with pytest.raises(CannotTell):
        release_backend.served_document(
            release("ghcr.io/tanercrb/eko-crm/backend:v1.2.0"), compose=double
        )
    assert double.calls == []


def test_eko115_k06_a_variable_only_the_previous_release_requires_does_not_stop_the_step() -> None:
    extra = "    environment:\n      GONE: ${A_VARIABLE_THE_HEAD_REMOVED:?required}\n"
    document, double = serve(release(extra=extra))
    assert document == DOCUMENT
    assert all("A_VARIABLE_THE_HEAD_REMOVED" not in text for text in double.files.values())


# C13's previous-release half reads the same record entry: only its backend digest reaches the lab


def test_eko115_k06_c13_takes_only_the_backend_digest_of_a_planted_entry(tmp_path: Path) -> None:
    entry = Release(tag="v1.2.0", commit=MAIN_OLDER, composition=composition(DIGEST))
    image = c13_previous_backend(RecordDouble({"v1.2.0": entry}), ReachDouble(), None)
    assert image == DIGEST
    text = "".join(
        f.read_text(encoding="utf-8")
        for service in ("backend", "migrate")
        for f in c13_lab(tmp_path)._with_image(service, image).extra_files
    )
    assert PLANTED not in text and "/host" not in text and DIGEST in text


def test_eko115_k06_c13_contrast_another_entry_gives_its_own_digest() -> None:
    entry = Release(tag="v1.2.0", commit=MAIN_OLDER, composition=composition(OTHER_DIGEST))
    image = c13_previous_backend(RecordDouble({"v1.2.0": entry}), ReachDouble(), None)
    assert image == OTHER_DIGEST
