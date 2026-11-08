"""EKO-1-19 K-01: the build-mode and release-mode sessions collect and skip the same node IDs, with
no failure or error in either; and the change set adds no mode branch to the runtime tests.

Base for the change-set check: $CHANGESET_BASE, else origin/main.
"""

import os
import subprocess
import sys

import pytest

from tests.static.test_k07_changeset import merge_base
from tests.support import mode_parity as mp
from tests.support import release_mode_ci as rm
from tests.support.repo import REPO_ROOT, git

BACKEND = REPO_ROOT / "backend"

STAMP = "2026-11-06T10:00:00.0000000Z "
BUILD = "\n".join(
    [
        "tests/runtime/test_a.py::test_one PASSED [ 33%]",
        "tests/runtime/test_a.py::test_two[x-1] PASSED [ 66%]",
        "tests/runtime/test_b.py::test_previous SKIPPED (no release) [100%]",
        "==== 2 passed, 1 skipped in 9.00s ====",
    ]
)


def session(*changes: tuple[str, str]) -> str:
    text = BUILD
    for old, new in changes:
        text = text.replace(old, new)
    return text


def test_eko119_k01_equal_sessions_pass() -> None:
    assert mp.parity_violations(BUILD, BUILD) == []


def test_eko119_k01_ci_log_timestamps_are_ignored() -> None:
    stamped = "\n".join(STAMP + line for line in BUILD.splitlines())
    assert mp.parity_violations(BUILD, stamped) == []


@pytest.mark.parametrize(
    "release",
    [
        # K-01 mutation (a): a backup test skips itself in release mode only.
        session(("test_one PASSED", "test_one SKIPPED (release mode)")),
        session(("test_two[x-1]", "test_two[x-2]")),
        session(("tests/runtime/test_a.py::test_one PASSED [ 33%]\n", "")),
        session(("test_one PASSED", "test_one XFAIL")),
        session(("test_one PASSED", "test_one FAILED")),
        session(
            (
                "test_two[x-1] PASSED [ 66%]",
                "test_two[x-1] PASSED [ 66%]\ntests/runtime/test_a.py::test_two[x-1] ERROR [ 66%]",
            )
        ),
    ],
    ids=["skipped-in-release", "mode-dependent-id", "not-collected", "xfail", "failed", "error"],
)
def test_eko119_k01_a_difference_between_the_modes_fails(release: str) -> None:
    assert mp.parity_violations(BUILD, release) != []


def test_eko119_k01_zero_collected_fails() -> None:
    assert mp.parity_violations("", "") != []


def test_eko119_k01_contrast_06945c3_release_mode_failures_are_found() -> None:
    """The v0.1.0 reversal: build mode green, release mode with failures and an error."""
    release = session(
        ("test_one PASSED", "test_one FAILED"),
        ("test_two[x-1] PASSED", "test_two[x-1] ERROR"),
    )
    found = mp.parity_violations(BUILD, release)
    assert any("failed" in line for line in found) and any("error" in line for line in found)


# The mode branch: K-01 edge, kills mutation (b) -------------------------------------------------

PLANTED_DIFF = """\
diff --git a/backend/tests/runtime/test_c15.py b/backend/tests/runtime/test_c15.py
--- a/backend/tests/runtime/test_c15.py
+++ b/backend/tests/runtime/test_c15.py
@@ -1,3 +1,5 @@
+    if os.environ.get("EKO_CHECKED_IMAGES"):
+        return
"""


def test_eko119_k01_planted_early_return_is_a_mode_branch() -> None:
    assert mp.mode_branch_lines(PLANTED_DIFF) != []


def test_eko119_k01_a_branch_on_the_override_is_a_mode_branch() -> None:
    diff = PLANTED_DIFF.replace('os.environ.get("EKO_CHECKED_IMAGES")', "checked_images_override()")
    assert mp.mode_branch_lines(diff) != []


def collected(env: dict[str, str]) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "-m", "runtime or previous_release", "tests/runtime"],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return [line for line in result.stdout.splitlines() if "::" in line]


def test_eko119_k01_runtime_node_ids_are_the_same_in_both_modes_and_every_session() -> None:
    build = {k: v for k, v in os.environ.items() if k != "EKO_CHECKED_IMAGES"}
    release = {**build, "EKO_CHECKED_IMAGES": " ".join(rm.CHECKED_PAIRS)}
    first = collected(build)
    assert first, "no runtime test collected"
    assert collected(build) == first
    assert collected(release) == first


def test_eko119_k01_change_set_adds_no_mode_branch_to_the_runtime_tests() -> None:
    diff = git("diff", "--unified=0", merge_base(), "--", "backend/tests/runtime/")
    assert mp.mode_branch_lines(diff) == []
