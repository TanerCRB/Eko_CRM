"""EKO-1-15 K-02 / K-03 edge, QA: `scripts/release-images.sh --self-test` cannot be thinned out
unnoticed.

The developer's contrasts accept any non-zero exit from a mutated copy, so a copy that crashed
(missing file, syntax error, exit 127) would count as caught. These contrasts demand exit 1 (the
self-test's own verdict) and the named case that guards the removed rule. They also cover rules
the developer's four contrasts do not: the recorded-ID check, all four images inspected, the tag
refused before any docker call, and a failed push ending the step.
"""

import subprocess
from pathlib import Path

import pytest

from tests.support.repo import REPO_ROOT, bash

SCRIPT = REPO_ROOT / "scripts" / "release-images.sh"
CASES_AT_CHECKPOINT = 23

# (rule removed, original text, mutated text, a self-test case that must fail)
MUTATIONS = [
    (
        "recorded ID required",
        '    [ -n "$want" ] || { echo "release-images: no recorded ID for $name" >&2; exit 2; }\n',
        "",
        "FAIL check-identity fails (2) when an ID was not recorded",
    ),
    (
        "every image inspected",
        "  local name want got\n  for name in $NAMES; do",
        "  local name want got\n  for name in backend frontend proxy; do",
        "FAIL check-identity inspects all four images",
    ),
    (
        "tag refused before any docker call",
        '  [[ "$tag" =~ $RELEASE_TAG_RE ]] || usage\n  check_identity\n',
        '  check_identity\n  [[ "$tag" =~ $RELEASE_TAG_RE ]] || usage\n',
        "FAIL push refuses the tag '1.2.0' (2) before any docker call",
    ),
    (
        "failed push ends the step",
        '    docker push --quiet "$target" >&2\n',
        '    docker push --quiet "$target" >&2 || true\n',
        "FAIL a failed third push ends the step non-zero",
    ),
]


def self_test(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bash(), script.as_posix(), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_eko115_k02_qa_self_test_runs_every_case_and_counts_honestly() -> None:
    result = self_test(SCRIPT)
    lines = result.stdout.splitlines()
    passed = [line for line in lines if line.startswith("ok   ")]
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(passed) >= CASES_AT_CHECKPOINT, f"self-test lost cases:\n{result.stdout}"
    summary = f"Self-test: {len(passed)} cases ran, {len(passed)} passed, 0 failed."
    assert lines[-1] == summary, result.stdout


@pytest.mark.parametrize(
    ("rule", "original", "removed", "failing_case"), MUTATIONS, ids=[m[0] for m in MUTATIONS]
)
def test_eko115_k02_qa_self_test_names_the_case_without_a_rule(
    tmp_path: Path, rule: str, original: str, removed: str, failing_case: str
) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count(original) == 1, f"the {rule} text is not in the script once"
    copy = tmp_path / "scripts" / "release-images.sh"
    copy.parent.mkdir()
    copy.write_text(source.replace(original, removed), encoding="utf-8", newline="\n")
    result = self_test(copy)
    assert result.returncode == 1, f"without the {rule}: exit {result.returncode}\n{result.stderr}"
    lines = result.stdout.splitlines()
    assert failing_case in lines, f"no case named for the {rule}:\n{result.stdout}"
    failed = sum(line.startswith("FAIL ") for line in lines)
    ran = failed + sum(line.startswith("ok   ") for line in lines)
    summary = f"Self-test: {ran} cases ran, {ran - failed} passed, {failed} failed."
    assert lines[-1] == summary, f"summary hides the failure without the {rule}:\n{result.stdout}"
