"""EKO-1-25 (#133) K-04: raising the runtime jobs' bound removes, skips, deselects or shortens no
runtime test. On the task's pinned pair, each `ci.yml` runtime job's own pytest command collects
the same non-empty set of runtime node IDs (with the same markers) at base and at head, both modes
collect the same set, and no path under `backend/tests/runtime/` changes.

The pair is read through Git objects only (tests/support/fixed_pair.py): never `$CHANGESET_BASE`,
`origin/main`, `HEAD` or the working tree. Collection runs on each commit's archived tree, with the
run line, `working-directory` and `env` its own `ci.yml` gives the job, so `addopts`, conftest
files and the marker expression are all those of the commit judged. Plants live in a throwaway
repository and are judged against two bases (the pinned base and the pinned head), so the verdict
does not depend on which base the live branch has.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.test_eko120_ci_timeout_retune import EKO_1_20_BASE
from tests.support.fixed_pair import ABSENT, REDIRECTION, Throwaway, archive_into, edit
from tests.support.repo import git

pytestmark = pytest.mark.usefixtures("real_repository_untouched")

# PR for EKO-1-25: its merge base, and the merge commit carrying the final ci.yml with both runtime
# bounds at 360. Copied from .task/pair (git rev-parse), never typed by hand.
BASE = "bf55c4d846d0d55a25b893736ab3b6bf6fa6256d"
HEAD = "4d1380ebda27015bbf927c12732d90f7d6ee4dc9"
BASES = (BASE, HEAD)
CI = ".github/workflows/ci.yml"
RUNTIME_JOBS = ("runtime", "runtime-checked")
RUNTIME_TESTS = "backend/tests/runtime/"
RUN_LINE = '        run: uv run pytest -m "runtime or previous_release" tests/runtime -v'
EXPIRY = "backend/tests/runtime/test_eko112_k04_event_expiry.py"
EXPIRY_ID = "tests/runtime/test_eko112_k04_event_expiry.py"

# Anything the shell would interpret: such a run line is not one plain pytest command.
SHELL_CONTROL = re.compile(r"[;&|<>`$\\\n]")
EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
SYNTHETIC = "synthetic-ci-expression"
# Caller shell settings that would change what pytest collects or which repository git reads.
NOT_INHERITED = (
    *REDIRECTION,
    "EKO_CHECKED_IMAGES",
    "RELEASE_RECORD_TOKEN",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTHONPATH",
)
PLUGIN = "eko125_collected"
PLUGIN_SOURCE = '''"""Writes every item pytest kept after deselection, with its marker names."""
import json
import os


def pytest_collection_finish(session):
    items = [[i.nodeid, sorted({m.name for m in i.iter_markers()})] for i in session.items]
    with open(os.environ["EKO125_COLLECTED"], "w", encoding="utf-8") as out:
        json.dump(items, out)
'''

Workflow = dict[Any, Any]
# Node ID -> sorted marker names, as one job's pytest command collects them.
Collected = dict[str, tuple[str, ...]]


class CollectionFailed(Exception):
    """A job's pytest command could not be turned into, or completed as, a collection."""


def pytest_step(flow: Workflow, job: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The job and its one step whose run line starts pytest."""
    found = (flow.get("jobs") or {}).get(job)
    if not isinstance(found, dict):
        raise CollectionFailed(f"{job}: no such job")
    steps = [s for s in found.get("steps") or [] if "pytest" in str(s.get("run", ""))]
    if len(steps) != 1:
        raise CollectionFailed(f"{job}: {len(steps)} steps run pytest, not one")
    return found, steps[0]


def pytest_args(run: str) -> list[str]:
    """The arguments of a run line that is exactly `uv run pytest <args>`."""
    line = run.strip()
    if SHELL_CONTROL.search(line):
        raise CollectionFailed(f"run line is not one plain command: {line!r}")
    words = shlex.split(line)
    if words[:3] != ["uv", "run", "pytest"]:
        raise CollectionFailed(f"run line does not start with `uv run pytest`: {line!r}")
    return words[3:]


def step_env(*blocks: Any) -> dict[str, str]:
    """Workflow, job and step `env`, a `${{ }}` expression replaced by a synthetic placeholder."""
    env: dict[str, str] = {}
    for block in blocks:
        for key, value in (block or {}).items():
            env[str(key)] = EXPRESSION.sub(SYNTHETIC, str(value))
    return env


def collect(tree: Path, job: str, scratch: Path) -> Collected:
    """What `job`'s own pytest command, as `tree`'s ci.yml writes it, collects in `tree`."""
    flow: Workflow = yaml.safe_load((tree / CI).read_text(encoding="utf-8"))
    found, step = pytest_step(flow, job)
    args = pytest_args(str(step["run"]))
    plugin_dir = scratch / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / f"{PLUGIN}.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    out = scratch / f"{tree.name}-{job}.json"
    out.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in NOT_INHERITED}
    env.update(step_env(flow.get("env"), found.get("env"), step.get("env")))
    env.update(PYTHONPATH=str(plugin_dir), PYTHONDONTWRITEBYTECODE="1", EKO125_COLLECTED=str(out))
    command = [sys.executable, "-m", "pytest", *args, "--collect-only", "-q"]
    command += ["-p", PLUGIN, "-p", "no:cacheprovider"]
    result = subprocess.run(
        command,
        cwd=tree / str(step.get("working-directory", ".")),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # 5: nothing collected, which the comparison reports; any other failure is not a collection.
    if result.returncode not in (0, 5) or not out.is_file():
        tail = "\n".join(result.stdout.splitlines()[-5:])
        raise CollectionFailed(f"{job}: pytest exited {result.returncode}: {tail}")
    items = json.loads(out.read_text(encoding="utf-8"))
    return {node: tuple(markers) for node, markers in items}


_COLLECTED: dict[str, dict[str, Collected] | str] = {}


def collected(commit: str, scratch: Path, cache: bool = True) -> dict[str, Collected] | str:
    """Both runtime jobs' collections in `commit`'s archived tree, or why they could not be made.
    A commit missing from the object store raises."""
    if cache and commit in _COLLECTED:
        return _COLLECTED[commit]
    where = scratch / f"{commit[:12]}-{len(list(scratch.iterdir()))}"
    tree = archive_into(commit, where / "tree")
    result: dict[str, Collected] | str
    try:
        result = {job: collect(tree, job, where) for job in RUNTIME_JOBS}
    except CollectionFailed as failure:
        result = f"collection failed: {failure}"
    if cache:
        _COLLECTED[commit] = result
    return result


def changed_paths(base: str, head: str, prefix: str) -> list[str]:
    """Paths under `prefix` that differ between two commits; a missing commit raises."""
    listed = git("diff", "--name-only", "--no-renames", "-z", base, head, "--", prefix)
    return sorted(p for p in listed.split("\0") if p)


def collection_violations(
    base: dict[str, Collected] | str, head: dict[str, Collected] | str
) -> list[str]:
    """Each runtime job collects at head exactly what it collects at base, neither is empty, and
    both modes collect the same set at head."""
    if isinstance(base, str) or isinstance(head, str):
        return [f"{side}: {found}" for side, found in (("base", base), ("head", head))
                if isinstance(found, str)]  # fmt: skip
    problems: list[str] = []
    for job in RUNTIME_JOBS:
        before, after = base[job], head[job]
        for side, found in (("base", before), ("head", after)):
            if not found:
                problems.append(f"{job}: {side} collects no runtime test")
        problems += [f"{job}: {n} no longer collected" for n in sorted(set(before) - set(after))]
        problems += [f"{job}: {n} newly collected" for n in sorted(set(after) - set(before))]
        problems += [
            f"{job}: {n} markers {before[n]} -> {after[n]}"
            for n in sorted(set(before) & set(after))
            if before[n] != after[n]
        ]
    if head[RUNTIME_JOBS[0]] != head[RUNTIME_JOBS[1]]:
        problems.append("head: the two modes do not collect the same set")
    return problems


def k04_violations(base: str, head: str, scratch: Path, cache: bool = True) -> list[str]:
    problems = collection_violations(
        collected(base, scratch, cache), collected(head, scratch, cache)
    )
    return problems + [f"{p} changes" for p in changed_paths(base, head, RUNTIME_TESTS)]


@pytest.fixture(scope="module")
def scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("eko125-k04")


# The claim on the pinned pair -----------------------------------------------------------------


def test_eko125_k04_runtime_collection_unchanged(scratch: Path) -> None:
    assert k04_violations(BASE, HEAD, scratch) == []
    head = collected(HEAD, scratch)
    assert not isinstance(head, str)
    assert all(head[job] for job in RUNTIME_JOBS)
    assert any(node.startswith(EXPIRY_ID) for node in head["runtime-checked"])


def test_eko125_k04_contrast_the_later_base_against_itself_holds(scratch: Path) -> None:
    assert k04_violations(HEAD, HEAD, scratch) == []


def test_eko125_k04_a_pair_commit_missing_from_the_object_store_raises(scratch: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        k04_violations(ABSENT, HEAD, scratch)


def test_eko125_k04_an_empty_collection_on_both_sides_is_not_equal() -> None:
    empty: dict[str, Collected] = {job: {} for job in RUNTIME_JOBS}
    found = collection_violations(empty, empty)
    assert "runtime: head collects no runtime test" in found
    assert "runtime-checked: base collects no runtime test" in found


# Plants, each alone, on the pinned head; judged against both bases ----------------------------


def job_edit(path: str, job: str, old: str, new: str) -> Callable[[Throwaway], None]:
    """Replace the first `old` inside one job's block of the workflow at `path`."""

    def change(repo: Throwaway) -> None:
        mode, _ = repo.entry(path)
        text = repo.text(path)
        start = text.index("\njobs:\n")
        start = text.index(f"\n  {job}:\n", start) + 1
        following = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start:])
        end = start + following.start() if following else len(text)
        block = text[start:end]
        assert old in block, (job, old)
        repo.put(path, repo.blob(text[:start] + block.replace(old, new, 1) + text[end:]), mode)

    return change


def put(path: str, content: str) -> Callable[[Throwaway], None]:
    return lambda repo: repo.put(path, repo.blob(content))


def both(*changes: Callable[[Throwaway], None]) -> Callable[[Throwaway], None]:
    def change(repo: Throwaway) -> None:
        for apply in changes:
            apply(repo)

    return change


ADDOPTS = "addopts = \"-m 'not runtime and not previous_release' --strict-markers"
SKIP_HOOK = """import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "event_expiry" in item.nodeid:
            item.add_marker(pytest.mark.skip(reason="planted"))
"""
NOTHING = '-m "runtime and not runtime"'
# Plant -> (change, a fragment the verdict must hold: the mechanism that kills it).
PLANTS: dict[str, tuple[Callable[[Throwaway], None], str]] = {
    "deselect-in-the-release-mode-run-line": (
        job_edit(CI, "runtime-checked", RUN_LINE, f"{RUN_LINE} --deselect {EXPIRY_ID}"),
        f"runtime-checked: {EXPIRY_ID}::",
    ),
    "k-in-the-composition-run-line": (
        job_edit(CI, "runtime", RUN_LINE, f'{RUN_LINE} -k "not event_expiry"'),
        f"runtime: {EXPIRY_ID}::",
    ),
    "narrowed-marker-expression": (
        job_edit(CI, "runtime", '-m "runtime or previous_release"', '-m "runtime"'),
        "no longer collected",
    ),
    "collect-ignore-in-a-conftest": (
        put("backend/tests/conftest.py", f'collect_ignore = ["{EXPIRY_ID[6:]}"]\n'),
        f"{EXPIRY_ID}::",
    ),
    "skip-marker-from-a-conftest": (
        put("backend/tests/conftest.py", SKIP_HOOK),
        "'skip')",
    ),
    "skip-marker-in-a-runtime-test": (
        edit(
            EXPIRY,
            "pytestmark = pytest.mark.runtime\n",
            'pytestmark = [pytest.mark.runtime, pytest.mark.skip(reason="planted")]\n',
        ),
        f"{EXPIRY} changes",
    ),
    "expiry-wait-shortened": (
        edit(EXPIRY, "EXPIRY_WAIT_SECONDS = 1500", "EXPIRY_WAIT_SECONDS = 600"),
        f"{EXPIRY} changes",
    ),
    "addopts-ignores-a-runtime-file": (
        edit("backend/pyproject.toml", ADDOPTS, f"{ADDOPTS} --ignore={EXPIRY_ID}"),
        f"{EXPIRY_ID}::",
    ),
    "empty-collection-in-both-modes": (
        both(
            job_edit(CI, "runtime", '-m "runtime or previous_release"', NOTHING),
            job_edit(CI, "runtime-checked", '-m "runtime or previous_release"', NOTHING),
        ),
        "head collects no runtime test",
    ),
}


@pytest.fixture
def throwaway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Throwaway:
    """Selected for every git call of the check; its origin/main is the pinned head."""
    return Throwaway(tmp_path / "repo", HEAD, monkeypatch)


@pytest.mark.parametrize("case", sorted(PLANTS))
def test_eko125_k04_each_plant_alone_fails_on_both_bases(
    case: str, throwaway: Throwaway, scratch: Path
) -> None:
    change, fragment = PLANTS[case]
    planted = throwaway.commit(HEAD, change)
    for base in BASES:
        found = k04_violations(base, planted, scratch)
        assert any(fragment in problem for problem in found), (case, base, found)


def test_eko125_k04_the_verdict_ignores_the_live_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scratch: Path
) -> None:
    """A repository whose HEAD, origin/main and $CHANGESET_BASE are all something else: the pair
    is still judged on itself, collected afresh rather than from the cache."""
    older = EKO_1_20_BASE  # long before this pair
    repo = Throwaway(tmp_path / "repo", older, monkeypatch)
    repo.checkout_files(older, CI)
    monkeypatch.setenv("CHANGESET_BASE", ABSENT)
    assert k04_violations(BASE, HEAD, scratch, cache=False) == []
    planted = repo.commit(HEAD, PLANTS["expiry-wait-shortened"][0])
    assert f"{EXPIRY} changes" in k04_violations(BASE, planted, scratch, cache=False)
