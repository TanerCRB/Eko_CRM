"""EKO-1-21 (#109): EKO-1-15's "no change under `backup/`" claim is judged on EKO-1-15's own change
set (PR #85: base 0e525b6^1, head 0e525b6^2), not on the live branch.

Every plant lives in a throwaway repository under `tmp_path` that borrows the real object store
through `objects/info/alternates`, selected for every `git` call by GIT_DIR/GIT_WORK_TREE: new
objects and refs land there, and the real `backup/` directory, which the runtime session builds
the backup image from, is never written.
"""

import inspect
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.runtime.test_eko115_k02_manifest_digests import eko_1_15_backup_changes
from tests.static.test_k07_changeset import changed_paths
from tests.support.repo import REPO_ROOT, git

pytestmark = pytest.mark.runtime

# PR #85's merge, recorded independently of the check's own constants.
EKO_1_15_MERGE = "0e525b6edb584ca0589cd7d64ae572f8aa9a582c"
PAIR_HEAD = "0d221229917c0fea3d7b99efaa3cce578e51087f"
ABSENT = "1" * 40
IDENTITY = {
    "GIT_AUTHOR_NAME": "plant",
    "GIT_AUTHOR_EMAIL": "plant@example.invalid",
    "GIT_COMMITTER_NAME": "plant",
    "GIT_COMMITTER_EMAIL": "plant@example.invalid",
}


class Throwaway:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        self.work = root / "work"
        git("init", "--quiet", str(self.work))
        self.git_dir = self.work / ".git"
        self.index_env: dict[str, str] = {}
        (self.git_dir / "objects" / "info" / "alternates").write_text(
            f"{Path(store, 'objects').as_posix()}\n", encoding="utf-8", newline="\n"
        )
        monkeypatch.setenv("GIT_DIR", str(self.git_dir))
        monkeypatch.setenv("GIT_WORK_TREE", str(self.work))
        for name, value in IDENTITY.items():
            monkeypatch.setenv(name, value)
        git("update-ref", "refs/remotes/origin/main", PAIR_HEAD)

    def checkout(self, commit: str) -> None:
        git("update-ref", "refs/heads/main", commit)
        git("symbolic-ref", "HEAD", "refs/heads/main")
        git("read-tree", "--reset", "-u", commit)

    def commit(self, parent: str, change: Callable[["Throwaway"], None]) -> str:
        """`parent`'s tree with one change applied through a private index."""
        index = self.git_dir / "plant.index"
        index.unlink(missing_ok=True)
        self.index_env = {"GIT_INDEX_FILE": str(index)}
        self._git("read-tree", parent)
        change(self)
        tree = self._git("write-tree").strip()
        return self._git("commit-tree", tree, "-p", parent, "-m", "plant").strip()

    def blob(self, content: str) -> str:
        return self._git("hash-object", "-w", "--stdin", stdin=content).strip()

    def entry(self, path: str) -> tuple[str, str]:
        [line] = self._git("ls-files", "-s", "--", path).splitlines()
        mode, oid, _ = line.split(" ", 2)
        return mode, oid

    def put(self, path: str, oid: str, mode: str = "100644") -> None:
        self._git("update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}")

    def remove(self, path: str) -> None:
        self._git("update-index", "--force-remove", "--", path)

    def _git(self, *args: str, stdin: str | None = None) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            env={**os.environ, **self.index_env},
            input=stdin,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    monkeypatch.delenv("CHANGESET_BASE", raising=False)
    return Throwaway(tmp_path, monkeypatch)


def modify(path: str) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        repo.put(path, repo.blob("planted\n"), mode)

    return change


def add(path: str) -> Callable[[Throwaway], None]:
    return lambda repo: repo.put(path, repo.blob("planted\n"))


def delete(path: str) -> Callable[[Throwaway], None]:
    return lambda repo: repo.remove(path)


def rename(source: str, target: str) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        mode, oid = repo.entry(source)
        repo.remove(source)
        repo.put(target, oid, mode)

    return change


def chmod(path: str) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        _, oid = repo.entry(path)
        repo.put(path, oid, "100755")

    return change


# K-01 -----------------------------------------------------------------------------------------

# (head, plant in the working tree, $CHANGESET_BASE): "planted" is the pair's head plus one
# committed change to backup/eko-backup; "origin" is origin/main of the throwaway repository.
LIVE_STATES = {
    "committed-base-unset": ("planted", False, None),
    "committed-base-empty": ("planted", False, ""),
    "committed-base-pr-sha": ("planted", False, "origin"),
    "worktree-base-unset": ("pair-head", True, None),
    "worktree-base-empty": ("pair-head", True, ""),
    "worktree-base-pr-sha": ("pair-head", True, "origin"),
    "base-with-other-backup-tree": ("planted", True, "planted"),
}


@pytest.mark.parametrize("state", sorted(LIVE_STATES))
def test_eko115_k02_backup_claim_ignores_a_live_change_set_under_backup(
    state: str, throwaway: Throwaway, monkeypatch: pytest.MonkeyPatch
) -> None:
    head, in_worktree, base = LIVE_STATES[state]
    planted = throwaway.commit(PAIR_HEAD, modify("backup/eko-backup"))
    throwaway.checkout(planted if head == "planted" else PAIR_HEAD)
    if in_worktree:
        (throwaway.work / "backup" / "eko-backup").write_text("worktree plant\n", encoding="utf-8")
        (throwaway.work / "backup" / "planted.txt").write_text("untracked\n", encoding="utf-8")
    if base is not None:
        commit = {"origin": PAIR_HEAD, "planted": planted}.get(base, base)
        monkeypatch.setenv("CHANGESET_BASE", commit)

    live = [p for p in changed_paths() if p.startswith("backup/")]
    assert live != [], "precondition: the live change set holds a path under backup/"
    assert eko_1_15_backup_changes() == []


# K-02 -----------------------------------------------------------------------------------------

FAILING = {
    "added": (add("backup/planted.txt"), "backup/planted.txt"),
    "modified": (modify("backup/eko-backup"), "backup/eko-backup"),
    "deleted": (delete("backup/schedule"), "backup/schedule"),
    "renamed-out": (rename("backup/README.md", "docs/backup-README.md"), "backup/README.md"),
    "mode-only": (chmod("backup/eko-backup"), "backup/eko-backup"),
}
PASSING = {
    "lab-module": modify("backend/tests/runtime/backup_lab.py"),
    "root-backup-md": add("backup.md"),
    "backupx": add("backupx/file"),
    "capitalised": add("Backup/x"),
}


@pytest.mark.parametrize("case", sorted(FAILING))
def test_eko115_k02_backup_claim_fails_on_one_change_inside_the_pair(
    case: str, throwaway: Throwaway
) -> None:
    change, path = FAILING[case]
    head = throwaway.commit(PAIR_HEAD, change)
    assert path in eko_1_15_backup_changes(head=head)


@pytest.mark.parametrize("case", sorted(PASSING))
def test_eko115_k02_backup_claim_contrast_a_prefix_twin_is_not_under_backup(
    case: str, throwaway: Throwaway
) -> None:
    head = throwaway.commit(PAIR_HEAD, PASSING[case])
    assert git("diff", "--name-only", PAIR_HEAD, head).strip() != "", "precondition: a change"
    assert eko_1_15_backup_changes(head=head) == []


def test_eko115_k02_backup_claim_contrast_the_unplanted_pair_passes(throwaway: Throwaway) -> None:
    assert eko_1_15_backup_changes(head=PAIR_HEAD) == []


# K-03 -----------------------------------------------------------------------------------------


def test_eko115_k02_backup_claim_reads_the_parents_of_pr_85s_merge() -> None:
    assert git("log", "-1", "--format=%s", EKO_1_15_MERGE).startswith("Merge pull request #85 ")
    parents = git("rev-parse", f"{EKO_1_15_MERGE}^1", f"{EKO_1_15_MERGE}^2").split()
    defaults = inspect.signature(eko_1_15_backup_changes).parameters
    pair = [defaults["base"].default, defaults["head"].default]
    assert pair == parents
    assert pair[0] != pair[1]


# K-04 -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["base", "head"])
def test_eko115_k02_backup_claim_errors_on_an_unavailable_commit(side: str) -> None:
    missing = subprocess.run(
        ["git", "cat-file", "-e", f"{ABSENT}^{{commit}}"], cwd=REPO_ROOT, capture_output=True
    )
    assert missing.returncode != 0, "precondition: the commit is not in the object store"
    with pytest.raises(subprocess.CalledProcessError):
        eko_1_15_backup_changes(**{side: ABSENT})
