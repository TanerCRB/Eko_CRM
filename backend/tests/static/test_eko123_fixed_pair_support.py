"""EKO-1-23 (#110) K-06, K-07: the helper that plants changes never writes the real repository, and
the new and rechecked tests run in the `backend` job (no `runtime` or `previous_release` marker).
"""

import ast
import os
import subprocess
from pathlib import Path

import pytest

from tests.support import fixed_pair
from tests.support.fixed_pair import REDIRECTION, Throwaway, add, leaked, snapshot
from tests.support.repo import REPO_ROOT

IDENTITY = ("-c", "user.name=plant", "-c", "user.email=plant@example.invalid")
NEW_AND_RECHECKED = (
    "test_eko123_already_inert.py",
    "test_eko123_eko113_claims.py",
    "test_eko123_fixed_pair_support.py",
    "test_eko123_workflow_claims.py",
    "test_adr0005_eko113_changeset.py",
    "test_eko115_k07_unchanged.py",
    "test_eko115_k07_unchanged_on_both_bases.py",
    "test_eko115_k07_qa_inside_allowed_steps_on_both_bases.py",
    "test_eko119_k03_release_mode_ci.py",
    "test_eko120_ci_timeout_retune.py",
)


def scratch(root: Path) -> Path:
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTION}

    def run(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *IDENTITY, *args], env=env, check=True, capture_output=True
        )

    root.mkdir()
    run("init", "--quiet")
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    run("add", "tracked.txt")
    run("commit", "--quiet", "-m", "one")
    return root


def test_eko123_snapshot_is_stable_when_nothing_is_written(tmp_path: Path) -> None:
    repo = scratch(tmp_path / "repo")
    assert snapshot(repo) == snapshot(repo)


@pytest.mark.parametrize("write", ["untracked-file", "modified-file", "head-moved", "staged-file"])
def test_eko123_snapshot_contrast_detects_a_write_to_the_repository(
    write: str, tmp_path: Path
) -> None:
    repo = scratch(tmp_path / "repo")
    before = snapshot(repo)
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTION}
    if write == "untracked-file":
        (repo / "planted.txt").write_text("x\n", encoding="utf-8")
    elif write == "modified-file":
        (repo / "tracked.txt").write_text("two\n", encoding="utf-8")
    elif write == "head-moved":
        subprocess.run(
            ["git", "-C", str(repo), *IDENTITY, "commit", "--allow-empty", "-m", "two", "-q"],
            env=env,
            check=True,
        )
    else:
        (repo / "staged.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "staged.txt"], env=env, check=True)
    assert leaked(before, snapshot(repo)) != []


def test_eko123_throwaway_plants_leave_the_real_repository_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = snapshot()
    pair_head = "947ff40efac06b13d6df48b6650024503f2e7308"
    repo = Throwaway(tmp_path / "repo", pair_head, monkeypatch)
    planted = repo.commit(pair_head, add("backend/planted.txt"))
    repo.checkout_files(planted, "backend/app")
    (repo.work / "backend" / "untracked.txt").write_text("x\n", encoding="utf-8")
    monkeypatch.undo()
    assert leaked(before, snapshot()) == []
    assert not (REPO_ROOT / "backend" / "planted.txt").exists()
    assert not (REPO_ROOT / "backend" / "untracked.txt").exists()


def test_eko123_new_and_rechecked_tests_carry_no_runtime_or_skip_marker() -> None:
    forbidden = {"runtime", "previous_release", "skip", "skipif", "xfail"}
    found = []
    for name in NEW_AND_RECHECKED:
        text = (Path(__file__).parent / name).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                found.append(f"{name}:{node.lineno} {node.attr}")
            if isinstance(node, ast.Attribute) and node.attr == "skip":
                found.append(f"{name}:{node.lineno} skip")
    assert found == []


def test_eko123_snapshot_ignores_a_ref_that_another_worktree_moves(tmp_path: Path) -> None:
    repo = scratch(tmp_path / "repo")
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTION}
    before = snapshot(repo)
    subprocess.run(["git", "-C", str(repo), "tag", "elsewhere"], env=env, check=True)
    subprocess.run(["git", "-C", str(repo), "branch", "other"], env=env, check=True)
    assert leaked(before, snapshot(repo)) == []


@pytest.mark.parametrize("redirected", [True, False], ids=["redirected", "redirection-dropped"])
def test_eko123_dropping_the_redirection_writes_the_repository_and_is_detected(
    redirected: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mutation, run against a scratch repository standing in for the real one."""
    repo = scratch(tmp_path / "repo")
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    monkeypatch.setattr(fixed_pair, "REPO_ROOT", repo)
    before = snapshot(repo)
    if not redirected:
        original = Throwaway._env

        def undirected(self: Throwaway) -> dict[str, str]:
            return {k: v for k, v in original(self).items() if k not in REDIRECTION}

        monkeypatch.setattr(Throwaway, "_env", undirected)
    Throwaway(tmp_path / "throwaway", head)
    assert (leaked(before, snapshot(repo)) == []) is redirected
