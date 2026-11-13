"""EKO-2-01 QA contrast for ADR-0003-C29's image half: the byte-for-byte comparison must read the
theme out of the image, not the repository twice.

The producer carrier's contrast flips a byte in memory after reading the image, so it would also
pass with an image reader that returned the repository copy. Here the one differing byte exists
only inside a fixture image built on top of the custom image, and the same comparison names it;
the unmodified image, read the same way, has no difference.
"""

import secrets
import subprocess
from pathlib import Path

import pytest

from tests.runtime.test_eko201_k07_theme_image import IMAGE, docker, image_theme
from tests.support import theme_checks as tc

pytestmark = pytest.mark.runtime

CHANGED = "login/resources/css/eko-crm.css"


def test_qa_k07_c29_a_byte_changed_only_inside_the_image_is_named(
    built_image: str, tmp_path: Path
) -> None:
    repository = tc.repository_theme()
    assert tc.byte_differences(repository, image_theme(built_image)) == []
    tag = f"localhost/eko-crm/eko201-fixture:theme-{secrets.token_hex(4)}"
    (tmp_path / "Dockerfile").write_text(
        f"FROM {IMAGE}\nUSER 0\n"
        f"RUN printf '/* eko201 fixture */\\n' >> {tc.IMAGE_THEME_DIR}/{CHANGED}\nUSER 1000\n",
        encoding="utf-8",
    )
    docker("build", "-q", "-t", tag, str(tmp_path), timeout=900)
    try:
        assert tc.byte_differences(repository, image_theme(tag)) == [f"{CHANGED}: bytes differ"]
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, check=False)
