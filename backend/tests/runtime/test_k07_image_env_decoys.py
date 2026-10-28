"""K-07 / ADR-0004-C9 image half: `.dockerignore` keeps `.env` files out of every built image (QA).

The CI images job plants a decoy `.env` at the root of each build context only. None of the four
Dockerfiles copies a context's root into the final image (backend copies `app/` and `migrations/`,
frontend only `dist/`, proxy and backup one file each), so a root decoy never reaches an image
whatever `.dockerignore` says: that check cannot fail. Here each context is copied from the files
Git would track, decoys are planted at the root and in every directory a Dockerfile copies into
the final image, the copy is built, and `scripts/image-check.sh` lists the image.

Contrast: the same build with the `.env` lines removed from the copy's `.dockerignore` (the copy,
never the repository) must be found by the same listing; otherwise the decoys prove nothing.
"""

import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.support.repo import REPO_ROOT, bash, git

pytestmark = pytest.mark.runtime

IMAGE_CHECK = REPO_ROOT / "scripts" / "image-check.sh"
# Context -> directories (relative to it) whose content reaches the final image, plus the root.
# `public/` does not exist yet: Vite copies it into dist/ verbatim once it does.
DECOY_DIRS = {
    "backend": ["", "app", "migrations"],
    "frontend": ["", "src", "public"],
    "proxy": [""],
    "backup": [""],
}
ENV_LINE = re.compile(r"^\s*(\*\*/)?\.env\*?\s*$")


def copy_context(context: str, target: Path) -> Path:
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", context)
    for relative in filter(None, listed.split("\0")):
        source = REPO_ROOT / relative
        if source.is_file():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return target / context


def plant_decoys(root: Path, directories: list[str]) -> None:
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / ".env").write_text("DECOY_ONLY=1\n", encoding="utf-8")


def build_and_check(root: Path, context: str) -> subprocess.CompletedProcess[str]:
    tag = f"eko-qa-decoy-{context}:{uuid.uuid4().hex[:8]}"
    built = subprocess.run(
        ["docker", "build", "-q", "-t", tag, str(root)],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert built.returncode == 0, built.stderr[-2000:]
    try:
        return subprocess.run(
            [bash(), str(IMAGE_CHECK), "--frontend", tag, tag],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


@pytest.mark.parametrize("context", sorted(DECOY_DIRS))
def test_k07_c9_no_planted_env_file_reaches_the_image(context: str, tmp_path: Path) -> None:
    root = copy_context(context, tmp_path)
    plant_decoys(root, DECOY_DIRS[context])
    result = build_and_check(root, context)
    assert "no .env file in" in result.stdout, result.stdout + result.stderr
    assert "FAIL no .env file" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("context", ["backend", "frontend"])
def test_k07_c9_contrast_without_the_env_lines_a_decoy_reaches_the_image(
    context: str, tmp_path: Path
) -> None:
    root = copy_context(context, tmp_path)
    ignore = root / ".dockerignore"
    kept = [
        line for line in ignore.read_text(encoding="utf-8").splitlines() if not ENV_LINE.match(line)
    ]
    ignore.write_text("\n".join(kept) + "\n", encoding="utf-8")
    plant_decoys(root, DECOY_DIRS[context])
    result = build_and_check(root, context)
    assert "FAIL no .env file" in result.stdout, result.stdout + result.stderr
