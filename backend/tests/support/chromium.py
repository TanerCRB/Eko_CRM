"""Install only the repository-authenticated Chromium archive for the current test host."""

import hashlib
import hmac
import json
import os
import platform
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

ARCHIVES = Path(__file__).with_name("chromium_archives.json")


class ArchiveDigestMismatch(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveSpec:
    url: str
    sha256: str
    executable: str


def current_archive() -> ArchiveSpec:
    machine = platform.machine().lower()
    normalized_machine = {"amd64": "x86_64", "x86_64": "x86_64"}.get(machine)
    if normalized_machine is None:
        raise RuntimeError(f"no authenticated Chromium archive for architecture {machine}")
    key = f"{platform.system().lower()}-{normalized_machine}"
    records = json.loads(ARCHIVES.read_text(encoding="utf-8"))
    record = records["platforms"].get(key)
    if record is None:
        raise RuntimeError(f"no authenticated Chromium archive for platform {key}")
    return ArchiveSpec(
        url=record["url"], sha256=record["sha256"], executable=record["executable"]
    )


def checked_member_destination(destination: Path, member_name: str) -> Path:
    member = PurePosixPath(member_name)
    if member.is_absolute() or ".." in member.parts or "\\" in member_name:
        raise ValueError(f"unsafe Chromium archive member: {member_name}")
    root = destination.resolve()
    target = (destination / Path(*member.parts)).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"unsafe Chromium archive member: {member_name}")
    return target


def prepare_chromium(
    archive_url: str, expected_sha256: str, destination: Path, executable_relative: str
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / "chromium.zip"
    digest = hashlib.sha256()
    with archive_path.open("wb+") as archive_file:
        with httpx.stream(
            "GET", archive_url, follow_redirects=True, timeout=120
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                archive_file.write(chunk)
                digest.update(chunk)
        actual_sha256 = digest.hexdigest()
        if not hmac.compare_digest(actual_sha256, expected_sha256):
            raise ArchiveDigestMismatch(
                f"Chromium archive SHA-256 {actual_sha256} did not match the repository record"
            )
        archive_file.seek(0)
        with zipfile.ZipFile(archive_file) as archive:
            for member in archive.infolist():
                checked_member_destination(destination, member.filename)
            archive.extractall(destination)

    executable = checked_member_destination(destination, executable_relative)
    if not executable.is_file():
        raise ValueError(f"authenticated Chromium archive has no {executable_relative}")
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def install_chromium(destination: Path) -> Path:
    spec = current_archive()
    return prepare_chromium(spec.url, spec.sha256, destination, spec.executable)
