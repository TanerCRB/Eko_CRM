"""EKO-1-15 K-02 / K-03 edge: `scripts/release-images.sh --self-test`, the built-in contrast
cases process-ci runs for every `scripts/*.sh` (no Docker daemon, no registry).

The contrasts run the self-test of a copy of the script with one rule removed: the self-test
exercises the copy's own modes, so a case that no longer catches the removed rule turns it red.
The real script gains no switch for this.
"""

import subprocess
from pathlib import Path

import pytest

from tests.support.repo import REPO_ROOT, bash

SCRIPT = REPO_ROOT / "scripts" / "release-images.sh"

# (rule removed, original line, line with the rule removed)
MUTATIONS = [
    (
        "identity comparison",
        'if [ "$got" != "$want" ]; then',
        "if false; then",
    ),
    (
        "release-tag form",
        '[[ "$tag" =~ $RELEASE_TAG_RE ]] || usage',
        "true",
    ),
    (
        "identity check before push",
        "  check_identity\n  for name in $NAMES; do\n    target=",
        "  for name in $NAMES; do\n    target=",
    ),
    (
        "missing registry digest",
        '[ -n "$digest" ] || { echo "release-images: no registry digest for $name" >&2; exit 1; }',
        "true",
    ),
]


def self_test(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bash(), script.as_posix(), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_eko115_k02_release_images_self_test_passes() -> None:
    result = self_test(SCRIPT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failed" in result.stdout.splitlines()[-1], result.stdout


@pytest.mark.parametrize(("rule", "original", "removed"), MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_eko115_k02_release_images_self_test_contrast_fails_without_a_rule(
    tmp_path: Path, rule: str, original: str, removed: str
) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count(original) == 1, f"the {rule} line is not in the script once"
    copy = tmp_path / "scripts" / "release-images.sh"
    copy.parent.mkdir()
    copy.write_text(source.replace(original, removed), encoding="utf-8", newline="\n")
    result = self_test(copy)
    assert result.returncode != 0, f"self-test stayed green without the {rule}:\n{result.stdout}"
