"""K-04 ADR-0001-C5 and K-07 ADR-0004-C9 image half, run on the composition's own images (QA).

`scripts/image-check.sh` was exercised only by its `--self-test` and the CI images job. Here it
runs on the images the runtime composition actually built, and its self-test (one bad image with
`node` and a `.env` file, one clean image, one missing image) is the contrast.
"""

import subprocess

import pytest

from tests.runtime.conftest import Started
from tests.support.repo import REPO_ROOT, bash

pytestmark = pytest.mark.runtime

IMAGE_CHECK = REPO_ROOT / "scripts" / "image-check.sh"
BUILT = ("frontend", "backend", "proxy", "backup")


def run_image_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bash(), str(IMAGE_CHECK), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_k04_image_check_self_test_finds_node_and_env_and_a_missing_image() -> None:
    result = run_image_check("--self-test")
    assert result.returncode == 0, result.stdout + result.stderr


def test_k04_adr0001_c5_and_c9_hold_on_the_images_the_composition_built(
    running: Started,
) -> None:
    images = {s: running.composition.inspect(s)["Config"]["Image"] for s in BUILT}
    result = run_image_check("--frontend", images["frontend"], *images.values())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("ok   ") == 1 + len(BUILT), result.stdout
