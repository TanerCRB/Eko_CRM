"""Browser archive authentication: only verified bytes may produce a launched executable."""

import functools
import hashlib
import http.server
import importlib
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def chromium() -> ModuleType:
    try:
        return importlib.import_module("tests.support.chromium")
    except ModuleNotFoundError as error:
        raise AssertionError("the shared verified Chromium archive installer is missing") from error


@pytest.fixture
def archive_url(tmp_path: Path) -> Iterator[str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/chromium.zip"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_archive(path: Path) -> bytes:
    executable = b"synthetic chromium executable"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("browser/chrome", executable)
    return executable


def test_matching_archive_is_accepted_and_extracts_the_expected_executable(
    tmp_path: Path, archive_url: str
) -> None:
    archive = tmp_path / "chromium.zip"
    executable = make_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    installed = chromium().prepare_chromium(
        archive_url, digest, tmp_path / "installed", "browser/chrome"
    )

    assert installed.read_bytes() == executable


def test_wrong_expected_digest_is_refused_before_an_executable_is_extracted(
    tmp_path: Path, archive_url: str
) -> None:
    archive = tmp_path / "chromium.zip"
    make_archive(archive)
    destination = tmp_path / "installed"

    with pytest.raises(chromium().ArchiveDigestMismatch):
        chromium().prepare_chromium(archive_url, "0" * 64, destination, "browser/chrome")

    assert not (destination / "browser" / "chrome").exists()


def test_tampered_archive_is_refused_before_an_executable_is_extracted(
    tmp_path: Path, archive_url: str
) -> None:
    archive = tmp_path / "chromium.zip"
    make_archive(archive)
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.write_bytes(archive.read_bytes() + b"tampered")
    destination = tmp_path / "installed"

    with pytest.raises(chromium().ArchiveDigestMismatch):
        chromium().prepare_chromium(archive_url, expected, destination, "browser/chrome")

    assert not (destination / "browser" / "chrome").exists()


def test_posix_zip_restores_executable_bits_for_browser_and_helpers(
    tmp_path: Path, archive_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "chromium.zip"
    members = {
        "browser/chrome": 0o100755,
        "browser/chrome_crashpad_handler": 0o100755,
        "browser/data.txt": 0o100644,
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, mode in members.items():
            member = zipfile.ZipInfo(name)
            member.create_system = 3
            member.external_attr = mode << 16
            archive.writestr(member, b"synthetic")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    chmod_calls: dict[str, int] = {}

    def record_chmod(path: Path, mode: int) -> None:
        chmod_calls[path.name] = mode & 0o111

    monkeypatch.setattr(chromium(), "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(Path, "chmod", record_chmod)
    chromium().prepare_chromium(archive_url, digest, tmp_path / "installed", "browser/chrome")

    assert chmod_calls == {"chrome": 0o111, "chrome_crashpad_handler": 0o111}
