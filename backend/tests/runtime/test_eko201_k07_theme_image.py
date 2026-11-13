"""EKO-2-01 K-07, image half: the theme inside the built custom image (ADR-0003-C29, ADR-0004-C35).

The image is built the composition's own way (`docker compose build keycloak`) and read
directly:

- C29: the theme directory inside the image holds the same files as the repository's, byte for
  byte, and passes the same rule set, with the parent checked against the login themes that
  image actually ships.
- C35: compared file by file with its official base (whose layers must be the image's lower
  layers), the image adds only the provider JAR, the boot-token seed and the theme files, plus
  the three re-augmentation outputs `kc.sh build` writes under `lib/quarkus`; an extra file in a
  fixture image on top of it is named. The theme files are not writable by the runtime user,
  and the same probe does detect a directory that user can write.
"""

import io
import re
import secrets
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.support import theme_checks as tc

pytestmark = pytest.mark.runtime
IMAGE = "localhost/eko-crm/keycloak:26.8.1-eko112"
BASE_REPOSITORY = "quay.io/keycloak/keycloak"
PROVIDER_JAR = "/opt/keycloak/providers/eko112-event-store-1.0.0.jar"
BOOT_SEED = "/etc/eko/keycloak-boot/.seed"
# `kc.sh build` re-augments the server for the selected provider (accepted 2026-11-06); these
# are its outputs, present in the base too and rewritten by the build.
BUILD_OUTPUTS = frozenset(
    f"/opt/keycloak/lib/quarkus/{name}"
    for name in ("generated-bytecode.jar", "quarkus-application.dat", "transformed-bytecode.jar")
)
# Written by the container runtime into every container, not by any image layer.
CONTAINER_FILES = frozenset({"/etc/hostname", "/etc/hosts", "/etc/resolv.conf", "/etc/mtab"})
THEMES_JAR = "/opt/keycloak/lib/lib/main/org.keycloak.keycloak-themes-26.8.1.jar"
PRUNE = r"find / -xdev \( -path /proc -o -path /sys -o -path /dev \) -prune -o"
# Regular files by content digest; symbolic links by their target (the base image holds
# dangling ones, which md5sum cannot read).
LISTING = f"{PRUNE} -type f -print0 | xargs -0 md5sum; {PRUNE} -type l -printf 'link:%l  %p\n'"


def docker(*args: str, timeout: int = 600) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=True)


def copy_out(image: str, path: str) -> bytes:
    container = docker("create", image).stdout.decode().strip()
    try:
        return docker("cp", f"{container}:{path}", "-").stdout
    finally:
        docker("rm", container)


def image_theme(image: str) -> dict[str, bytes]:
    return tc.theme_from_tar(copy_out(image, tc.IMAGE_THEME_DIR), prefix=f"{tc.THEME_NAME}/")


def shipped_parents(image: str) -> frozenset[str]:
    with tarfile.open(fileobj=io.BytesIO(copy_out(image, THEMES_JAR))) as tar:
        member = tar.extractfile(tar.getmembers()[0])
        assert member is not None
        jar = zipfile.ZipFile(io.BytesIO(member.read()))
    found = {
        match.group(1)
        for name in jar.namelist()
        if (match := re.fullmatch(r"theme/([^/]+)/login/theme\.properties", name))
    }
    return frozenset(found)


def digests(image: str) -> dict[str, str]:
    listing = docker("run", "--rm", "-u", "0", "--entrypoint", "sh", image, "-c", LISTING).stdout
    found = {}
    for line in listing.decode("utf-8", "replace").splitlines():
        digest, _, path = line.partition("  ")
        if path and path not in CONTAINER_FILES:
            found[path] = digest
    return found


def layers(image: str) -> list[str]:
    out = docker(
        "image", "inspect", "--format", "{{range .RootFS.Layers}}{{println .}}{{end}}", image
    )
    return out.stdout.decode().split()


def official_base() -> str:
    """The official base the Dockerfile names, by repository and its pinned version."""
    text = tc.DOCKERFILE.read_text(encoding="utf-8")
    return BASE_REPOSITORY + ":" + tc.base_version(text)


def changes_against_base(image: str) -> set[str]:
    base = official_base()
    if layers(base) != layers(image)[: len(layers(base))]:
        # The tag may have moved upstream since this host last pulled it; the build used the
        # current one, so the comparison must too.
        docker("pull", "-q", base, timeout=1200)
    base_layers = layers(base)
    assert base_layers == layers(image)[: len(base_layers)], "the image is not built on its base"
    before, after = digests(base), digests(image)
    return {path for path in set(before) | set(after) if before.get(path) != after.get(path)}


def allowed_changes() -> set[str]:
    theme = {f"{tc.IMAGE_THEME_DIR}/{name}" for name in tc.repository_theme()}
    return {PROVIDER_JAR, BOOT_SEED, *theme, *BUILD_OUTPUTS}


def test_k07_c29_image_copy_equals_the_repository_byte_for_byte_and_passes(
    built_image: str,
) -> None:
    repository = tc.repository_theme()
    image = image_theme(built_image)
    assert image, "no theme inside the image"
    assert tc.byte_differences(repository, image) == []
    parents = shipped_parents(built_image)
    assert {"base", "keycloak.v2"} <= parents
    assert tc.theme_violations(image, parents) == []
    name = "login/theme.properties"
    changed = {**image, name: image[name][:-1] + bytes([image[name][-1] ^ 1])}
    assert tc.byte_differences(repository, changed) == [f"{name}: bytes differ"]


def test_c35_image_adds_only_the_provider_the_seed_and_the_theme(built_image: str) -> None:
    changes = changes_against_base(built_image)
    allowed = allowed_changes()
    assert sorted(changes - allowed) == []
    # Each permitted addition is really there: the provider, the seed and every theme file.
    assert sorted((allowed - BUILD_OUTPUTS) - changes) == []


def test_c35_an_extra_file_copied_into_a_fixture_image_is_named(
    built_image: str, tmp_path: Path
) -> None:
    tag = f"localhost/eko-crm/eko201-fixture:extra-{secrets.token_hex(4)}"
    (tmp_path / "extra.txt").write_text("eko201 fixture\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text(
        f"FROM {IMAGE}\nCOPY extra.txt /opt/keycloak/conf/eko201-extra.txt\n", encoding="utf-8"
    )
    docker("build", "-q", "-t", tag, str(tmp_path), timeout=900)
    try:
        extra = changes_against_base(tag) - allowed_changes()
        assert extra == {"/opt/keycloak/conf/eko201-extra.txt"}
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, check=False)


def test_c35_theme_files_are_not_writable_by_the_runtime_user(built_image: str) -> None:
    script = (
        "id -u; echo theme:; find /opt/keycloak/themes/eko-crm -writable; "
        "echo control:; find /opt/keycloak/providers -maxdepth 0 -writable"
    )
    out = docker("run", "--rm", "--entrypoint", "sh", built_image, "-c", script).stdout.decode()
    uid, rest = out.split("\n", 1)
    theme, control = rest.split("control:", 1)
    assert uid.strip() == "1000"
    assert theme.replace("theme:", "").strip() == "", "a theme path is writable by uid 1000"
    assert control.strip() == "/opt/keycloak/providers", "the probe does not detect writability"
