"""Fixed base/head pairs of merged tasks, and the throwaway repository their claims are planted in.

A claim about one past change set is judged on that task's own pair, read through Git objects
only: never `$CHANGESET_BASE`, `origin/main`, `HEAD` or the working tree. A commit that is not in
the object store raises (`git` exits non-zero); nothing here returns an empty result or skips.

The throwaway repository borrows the real object store through `objects/info/alternates` and is
selected for every `git` call by GIT_DIR/GIT_WORK_TREE, so new objects and refs land in it and the
real repository is never written. It also works from a git worktree (`--git-common-dir`). This
module imports no runtime fixture and nothing from `app/`.
"""

import hashlib
import os
import subprocess
import tarfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pytest

from tests.support.repo import REPO_ROOT, git

ABSENT = "1" * 40
IDENTITY = {
    "GIT_AUTHOR_NAME": "plant",
    "GIT_AUTHOR_EMAIL": "plant@example.invalid",
    "GIT_COMMITTER_NAME": "plant",
    "GIT_COMMITTER_EMAIL": "plant@example.invalid",
}
REDIRECTION = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")


def require_commit(commit: str, env: dict[str, str] | None = None) -> str:
    """The full SHA of `commit`; raises CalledProcessError when the object store lacks it."""
    return subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def file_at(commit: str, path: str) -> str | None:
    """`path` as stored in `commit`; None only when the commit exists and holds no such file."""
    require_commit(commit)
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else None


def archive_into(commit: str, target: Path, *paths: str, env: dict[str, str] | None = None) -> Path:
    """Extract `paths` of `commit` under `target`; raises when the commit is missing."""
    require_commit(commit, env)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit, *paths],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        tar.extractall(target, filter="data")
    return target


# Every (ref, value) a Throwaway asked git to write; the real repository must hold none of them.
WRITES: list[tuple[str, str]] = []
PLANT_REFS = ("refs/heads/main", "refs/remotes/origin/main")


def _real(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTION}
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else ""


def snapshot(root: Path = REPO_ROOT) -> dict[str, str]:
    """What a plant could write to the repository at `root` (K-07), taken without any GIT_DIR
    redirection: this worktree's files, its HEAD and index, and the refs a Throwaway writes.
    Refs that other worktrees of the shared repository move are deliberately not compared."""
    index = Path(_real(root, "rev-parse", "--path-format=absolute", "--git-path", "index").strip())
    return {
        "status": _real(root, "status", "--porcelain", "--untracked-files=all"),
        "head": _real(root, "symbolic-ref", "-q", "HEAD") + _real(root, "rev-parse", "HEAD"),
        "index": hashlib.sha256(index.read_bytes()).hexdigest() if index.is_file() else "",
        **{ref: _real(root, "rev-parse", "-q", "--verify", ref).strip() for ref in PLANT_REFS},
    }


def leaked(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Differences a plant could have caused: any change of this worktree, or a plant ref that
    now holds a value a Throwaway wrote (a move by another worktree holds some other value)."""
    written = {value for _, value in WRITES}
    found = [k for k in ("status", "head", "index") if before[k] != after[k]]
    return found + [r for r in PLANT_REFS if after[r] != before[r] and after[r] in written]


class Throwaway:
    """An empty repository under `root`; its object store reads through the real one.

    Its own operations name the repository in their environment; `select` additionally redirects
    the process (GIT_DIR/GIT_WORK_TREE) so that the checks under test read it instead.
    """

    def __init__(
        self, root: Path, origin: str, monkeypatch: pytest.MonkeyPatch | None = None
    ) -> None:
        store = git(
            "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=REPO_ROOT
        ).strip()
        self.work = root / "work"
        git("init", "--quiet", str(self.work))
        self.git_dir = self.work / ".git"
        self.index_env: dict[str, str] = {}
        (self.git_dir / "objects" / "info" / "alternates").write_text(
            f"{Path(store, 'objects').as_posix()}\n", encoding="utf-8", newline="\n"
        )
        self._git("update-ref", "refs/remotes/origin/main", origin)
        if monkeypatch is not None:
            self.select(monkeypatch)

    def select(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_DIR", str(self.git_dir))
        monkeypatch.setenv("GIT_WORK_TREE", str(self.work))
        for name, value in IDENTITY.items():
            monkeypatch.setenv(name, value)
        redirected = Path(git("rev-parse", "--path-format=absolute", "--git-dir").strip())
        if redirected.resolve() != self.git_dir.resolve():
            raise RuntimeError("the throwaway repository is not the one git selects")

    def checkout(self, commit: str) -> None:
        self._git("update-ref", "refs/heads/main", commit)
        self._git("symbolic-ref", "HEAD", "refs/heads/main")
        self._git("read-tree", "--reset", "-u", commit)

    def checkout_files(self, commit: str, *paths: str) -> None:
        """HEAD and the index at `commit`, but only `paths` written to the working tree: enough
        for a claim that reads those files, and much cheaper than a whole checkout."""
        self._git("update-ref", "refs/heads/main", commit)
        self._git("symbolic-ref", "HEAD", "refs/heads/main")
        self._git("read-tree", "--reset", commit)
        archive_into(commit, self.work, *paths, env=self._env())

    def commit(self, parent: str, change: Callable[["Throwaway"], None]) -> str:
        """`parent`'s tree with one change applied through a private index."""
        index = self.git_dir / "plant.index"
        index.unlink(missing_ok=True)
        self.index_env = {"GIT_INDEX_FILE": str(index)}
        self._git("read-tree", parent)
        change(self)
        tree = self._git("write-tree").strip()
        commit = self._git("commit-tree", tree, "-p", parent, "-m", "plant").strip()
        self.index_env = {}
        return commit

    def blob(self, content: str) -> str:
        return self._git("hash-object", "-w", "--stdin", stdin=content).strip()

    def entry(self, path: str) -> tuple[str, str]:
        [line] = self._git("ls-files", "-s", "--", path).splitlines()
        mode, oid, _ = line.split(" ", 2)
        return mode, oid

    def text(self, path: str) -> str:
        return self._git("show", f":{path}")

    def put(self, path: str, oid: str, mode: str = "100644") -> None:
        self._git("update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}")

    def remove(self, path: str) -> None:
        self._git("update-index", "--force-remove", "--", path)

    def _env(self) -> dict[str, str]:
        return {
            **os.environ,
            **IDENTITY,
            "GIT_DIR": str(self.git_dir),
            "GIT_WORK_TREE": str(self.work),
            **self.index_env,
        }

    def _git(self, *args: str, stdin: str | None = None) -> str:
        env = self._env()
        if args[0] == "update-ref":
            WRITES.append((args[1], args[2]))
        # Bytes in and out: text mode would write each line feed of a blob as CRLF on Windows.
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            env=env,
            input=None if stdin is None else stdin.encode("utf-8"),
            check=True,
            capture_output=True,
        )
        return result.stdout.decode("utf-8")


def modify(path: str) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        repo.put(path, repo.blob("planted\n"), mode)

    return change


def edit(path: str, old: str, new: str) -> Callable[[Throwaway], None]:
    """Replace the first `old` in `path`, which must be there."""

    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        assert old in text, (path, old)
        repo.put(path, repo.blob(text.replace(old, new, 1)), mode)

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
