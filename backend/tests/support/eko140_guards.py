"""EKO-1-40 (#228) K-05 and K-06, QA: the guarded-line check and the path check of the task's PR.

    uv run python -m tests.support.eko140_guards k05 <base-sha> <head-sha>
    uv run python -m tests.support.eko140_guards k06 <base-sha> <head-sha>

Both judge `git diff base...head` (from the merge base of the two, to head) between two explicit
full SHAs, never the live PR base, origin/main, HEAD or the working tree. A base at a later main
that already holds head gives an empty difference (inert after merge). Renames are not detected,
so a renamed file is its old path deleted and its new path added. Exit 0 = nothing found, 1 = a
finding, 2 = the check could not run (never read 2 as a pass).

K-05 compares each guarded item of a file the change set touches with the same item at `PINNED`
(`b099acc`, the carrier as EKO-1-38 merged it): a guarded line must occur in its function as often
as there, a guarded function or file must be byte-identical, an additions-only file may lose no
line, and a touched file may not gain a retry around the carrier's run or sends, a rerun marker or
plugin name, or a `find` that loops or catches. The send schedule is guarded byte-identical: G-A A
would allow a named change backed by the record, but this change set names none (G-1), so the
stricter rule judges it. K-06 holds the change set to the criterion's allowed set and names every
path under a forbidden prefix.
"""

import ast
import functools
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from tests.support.fixed_pair import require_commit
from tests.support.repo import git

# EKO-1-38's merge (PR #229): the carrier, the EKO-1-38 tests and the fixture apps K-05 pins.
PINNED = "b099acc42ed6fbbe82e52deb41d0bae37d25fea2"
CARRIER = "backend/tests/runtime/eko201/test_eko201_k04_refresh_concurrency.py"
PROCESSES = "backend/tests/runtime/eko201/processes.py"
OBSERVED_APP = "backend/tests/support/eko138_observed_app.py"
FIXTURE_APP = "backend/tests/support/eko201_fixture_app.py"
CARRIER_TEST = "test_k04_pool_exhausted_responsive_identity_server_serves_every_request"
RESPONSIVE = "pool_exhausted_responsive"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
RERUN = re.compile(r"\b(flaky|reruns?|rerunfailures|rerun_except|pytest_retry|tenacity|stamina)\b")
RETRIED_CALLS = {RESPONSIVE, "send_tagged"}
# This check and its fixture tests name the rerun tokens and plant them; they are not scanned.
SELF = (
    "backend/tests/support/eko140_guards.py",
    "backend/tests/runtime/eko201/test_eko140_qa_k05_k06_guards.py",
)


class CannotJudge(Exception):
    """The pair cannot be judged: never a pass."""


def commit(sha: str) -> str:
    if not FULL_SHA.fullmatch(sha):
        raise CannotJudge(f"{sha!r} is not a full 40-character SHA")
    if require_commit(sha) != sha:
        raise CannotJudge(f"{sha} is not a commit")
    return sha


# Read through full SHAs only (`commit`, `git merge-base`, `PINNED`): a commit's content never
# changes, so a cached read is the same read in any repository that holds the commit.
@functools.cache
def entry_at(at: str, path: str) -> str:
    """Mode, object id and path of `path` at `at`; empty when `at` holds no such file."""
    return git("ls-tree", at, "--", path)


@functools.cache
def text_at(at: str, path: str) -> str | None:
    """`path` as stored in `at`; None when `at` holds no such file."""
    if not entry_at(at, path).strip():
        return None
    return git("show", f"{at}:{path}")


def removed_lines(base: str, head: str, path: str) -> int:
    """Lines of `path` removed or modified in `base...head`; a binary diff counts as one."""
    numstat = git("diff", "--numstat", "--no-renames", f"{base}...{head}", "--", path).split("\t")
    if len(numstat) < 2:
        return 0
    return int(numstat[1]) if numstat[1].isdigit() else 1


def changes(base: str, head: str) -> list[tuple[str, str]]:
    """(status, path) of every file `base...head` changes."""
    fields = git("diff", "--name-status", "--no-renames", "-z", f"{base}...{head}").split("\0")
    return list(zip(fields[0:-1:2], fields[1::2], strict=True))


@functools.cache
def segment(source: str | None, function: str | None) -> str | None:
    """The top-level `function` of `source`, decorators excluded; the whole source for None."""
    if source is None or function is None:
        return source
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            return "".join(lines[node.lineno - 1 : node.end_lineno])
    return None


# K-05 --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Context:
    base: str
    head: str
    merge: str
    changed: dict[str, str]  # path -> status


Judge = Callable[[Context], list[str]]


@dataclass(frozen=True)
class Item:
    name: str
    path: str  # the file whose change makes the item judged; "" for every touched file
    judge: Judge


def line(path: str, function: str | None, text: str) -> Judge:
    """`text` occurs in `function` of `path` at head as often as at `PINNED`."""

    def judge(ctx: Context) -> list[str]:
        pinned = segment(text_at(PINNED, path), function)
        if pinned is None or text not in pinned:
            raise CannotJudge(f"{path}: {text!r} is not in {function or 'the file'} at {PINNED}")
        found = segment(text_at(ctx.head, path), function) or ""
        if found.count(text) == pinned.count(text):
            return []
        where = function or "the file"
        return [f"{path}: {text!r} in {where} is not as at {PINNED[:7]}"]

    return judge


def function_unchanged(path: str, function: str) -> Judge:
    def judge(ctx: Context) -> list[str]:
        pinned = segment(text_at(PINNED, path), function)
        if pinned is None:
            raise CannotJudge(f"{path}: no function {function} at {PINNED}")
        if segment(text_at(ctx.head, path), function) == pinned:
            return []
        return [f"{path}: {function} is not byte-identical to {PINNED[:7]}"]

    return judge


def file_unchanged(path: str) -> Judge:
    def judge(ctx: Context) -> list[str]:
        pinned = entry_at(PINNED, path)
        if not pinned:
            raise CannotJudge(f"{path}: not in {PINNED}")
        if entry_at(ctx.head, path) == pinned:
            return []
        return [f"{path}: not byte-identical to {PINNED[:7]}"]

    return judge


def additions_only(path: str) -> Judge:
    def judge(ctx: Context) -> list[str]:
        removed = removed_lines(ctx.base, ctx.head, path)
        if ctx.changed.get(path) == "M" and removed == 0:
            return []
        return [
            f"{path}: additions only; {ctx.changed[path]}, {removed} line(s) removed or changed"
        ]

    return judge


def _names(node: ast.AST) -> set[str]:
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


@functools.cache
def _retries(source: str | None) -> int:
    """Loops and try statements of `source` around a call of the carrier's run or sends."""
    if source is None:
        return 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 1
    statements = (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, statements) and _names(node) & RETRIED_CALLS
    )


def no_retry_around_the_run(ctx: Context) -> list[str]:
    """Scoped to the carrier file: the K-01 test wraps the run in `pytest.raises` legitimately."""
    if _retries(text_at(ctx.head, CARRIER)) <= _retries(text_at(PINNED, CARRIER)):
        return []
    return [f"{CARRIER}: a loop or try around {sorted(RETRIED_CALLS)}"]


def touched_backend(ctx: Context) -> list[str]:
    """Every file under `backend/` the change set adds or modifies, this check's own excluded."""
    return [
        p for p, s in ctx.changed.items() if s != "D" and p.startswith("backend/") and p not in SELF
    ]


def no_rerun(ctx: Context) -> list[str]:
    found = []
    for path in touched_backend(ctx):
        before = len(RERUN.findall(text_at(ctx.merge, path) or ""))
        if len(RERUN.findall(text_at(ctx.head, path) or "")) > before:
            found.append(f"{path}: a rerun marker or plugin name added")
    return found


@functools.cache
def _retrying_finds(source: str | None) -> int:
    """`find` functions that loop or catch: a `find` the application does not retry, retried."""
    if source is None:
        return 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 1
    loops = (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name == "find"
        and any(isinstance(sub, loops) for sub in ast.walk(node))
    )


def no_retrying_find(ctx: Context) -> list[str]:
    found = []
    for path in touched_backend(ctx):
        if not path.endswith(".py"):
            continue
        before = _retrying_finds(text_at(ctx.merge, path))
        if _retrying_finds(text_at(ctx.head, path)) > before:
            found.append(f"{path}: a find that loops or catches")
    return found


EKO138_TESTS = (
    "backend/tests/runtime/eko201/test_eko138_k01_late_request.py",
    "backend/tests/runtime/eko201/test_eko138_qa_holder_on_b.py",
    "backend/tests/runtime/eko201/test_eko138_qa_waiting_not_arrived.py",
)
NEIGHBOURS = (
    "test_k04_ten_concurrent_requests_share_one_refresh",
    "test_k04_one_request_refreshes_once",
    "test_k04_hanging_identity_server_gives_every_request_503_within_six_seconds",
    "_pool_exhausted_hang",
    "test_k04_pool_exhausted_hanging_identity_server_still_answers_503_within_six_seconds",
    "test_k04_opposite_without_the_checkout_bound_exceeds_six_seconds",
    "test_k04_two_sessions_refresh_independently",
)
OBSERVED = 'OBSERVED = "tests.support.eko138_observed_app:create_with_blockers"'

ITEMS: tuple[Item, ...] = (
    # DoD 4: the four assertions of the carrier.
    Item(
        "ten-statuses-200",
        CARRIER,
        line(CARRIER, CARRIER_TEST, "assert [o.status for o in outcomes] == [200] * 10, outcomes"),
    ),
    Item(
        "one-refresh", CARRIER, line(CARRIER, CARRIER_TEST, "assert len(stub.refreshes(sid)) == 1")
    ),
    Item(
        "no-superseded", CARRIER, line(CARRIER, CARRIER_TEST, "assert stub.superseded_uses() == []")
    ),
    Item("one-session-row", CARRIER, line(CARRIER, CARRIER_TEST, "assert session_count(pg) == 1")),
    # The EKO-1-38 assertions and the observed precondition.
    Item(
        "refresh-at-block",
        CARRIER,
        line(CARRIER, CARRIER_TEST, "assert run.refresh_at_block == [None], (refresh, run.marks)"),
    ),
    Item(
        "pools-full",
        CARRIER,
        line(CARRIER, CARRIER_TEST, "assert all(c == p and h == p for c, h, p in full.values())"),
    ),
    Item(
        "hold-after-precondition",
        CARRIER,
        line(CARRIER, CARRIER_TEST, "assert hold_after(run, first) >= POOL_TIMEOUT_SECONDS,"),
    ),
    Item(
        "observed-precondition",
        CARRIER,
        line(
            CARRIER,
            "all_waiting",
            "if refreshes == [None] and sum(holding.values()) == 1 and waiting == WAITERS:",
        ),
    ),
    # Bounds and timings.
    Item("bound", CARRIER, line(CARRIER, None, "\nBOUND = 6.0\n")),
    Item("waiters", CARRIER, line(CARRIER, None, "\nWAITERS = 9\n")),
    Item("refresh-delay", CARRIER, line(CARRIER, RESPONSIVE, "stub.refresh_delay_seconds = 2.0")),
    Item(
        "hold",
        CARRIER,
        line(CARRIER, RESPONSIVE, "time.sleep(max(0.0, 1.5 - (time.monotonic() - started)))"),
    ),
    Item(
        "all-waiting-deadline",
        CARRIER,
        line(CARRIER, "all_waiting", "deadline = time.monotonic() + 10"),
    ),
    # The pool the carrier's processes get.
    Item(
        "carrier-backends-call",
        CARRIER,
        line(CARRIER, RESPONSIVE, "with backends(pg, stub, factory=factory) as (a, b):"),
    ),
    Item("pool-size-default", PROCESSES, line(PROCESSES, "backend_env", "pool_size: int = 2,")),
    Item("max-overflow", PROCESSES, line(PROCESSES, "backend_env", "**pg.app_env(pool_size, 0),")),
    # The undelayed carrier cases run the observed factory, never the delay factory.
    Item("observed-factory", CARRIER, line(CARRIER, None, OBSERVED)),
    Item(
        "default-factory",
        CARRIER,
        line(CARRIER, RESPONSIVE, "late: float | None, factory: str = OBSERVED"),
    ),
    Item(
        "carrier-call",
        CARRIER,
        line(
            CARRIER, CARRIER_TEST, "run = pool_exhausted_responsive(pg, stub, all_waiting, late)\n"
        ),
    ),
    # The send schedule (G-A A, no change named): when each request is sent.
    Item(
        "send-order",
        CARRIER,
        line(CARRIER, RESPONSIVE, "pool.submit(send_tagged, t, session, i, stub, late, started)"),
    ),
    Item("send-tagged", CARRIER, function_unchanged(CARRIER, "send_tagged")),
    # Neighbouring tests and every EKO-1-38 test file.
    *(Item(f"neighbour:{name}", CARRIER, function_unchanged(CARRIER, name)) for name in NEIGHBOURS),
    *(
        Item(f"eko138:{path.rsplit('/', 1)[1]}", path, file_unchanged(path))
        for path in EKO138_TESTS
    ),
    # The observation and fixture apps: additions only.
    Item("additions-only:eko138_observed_app", OBSERVED_APP, additions_only(OBSERVED_APP)),
    Item("additions-only:eko201_fixture_app", FIXTURE_APP, additions_only(FIXTURE_APP)),
    # No retry, rerun or retrying find.
    Item("no-retry-around-the-run", CARRIER, no_retry_around_the_run),
    Item("no-rerun", "", no_rerun),
    Item("no-retrying-find", "", no_retrying_find),
)


def context(base: str, head: str) -> Context:
    base, head = commit(base), commit(head)
    merge = git("merge-base", base, head).strip()
    return Context(base, head, merge, {p: s for s, p in changes(base, head)})


def guard_violations(base: str, head: str, items: tuple[Item, ...] = ITEMS) -> list[str]:
    ctx = context(base, head)
    problems = []
    for item in items:
        if item.path and item.path not in ctx.changed:
            continue
        problems += [f"[{item.name}] {problem}" for problem in item.judge(ctx)]
    return problems


# K-06 --------------------------------------------------------------------------------------------

FORBIDDEN = (
    "backend/app/",
    "backend/migrations/",
    "frontend/",
    "backend/tests/runtime/conftest.py",
)
PLAN = "docs/PLAN.md"
OUTSIDE = "outside the allowed set"
PLAN_ADDED_ONLY = "may change by added lines only"


def allowed(status: str, path: str) -> bool:
    return (
        path.startswith("backend/tests/runtime/eko201/")
        or re.fullmatch(r"backend/tests/support/eko140_[^/]+\.py", path) is not None
        or (status == "M" and path in (OBSERVED_APP, FIXTURE_APP))
        or path.startswith("docs/evidence/EKO-1-40/")
        or path.startswith("docs/cost-register/")
    )


def path_violations(base: str, head: str, forbidden: tuple[str, ...] = FORBIDDEN) -> list[str]:
    ctx = context(base, head)
    problems = []
    for path, status in ctx.changed.items():
        if path == PLAN and status == "M":
            removed = removed_lines(ctx.base, ctx.head, path)
            if removed:
                problems.append(
                    f"M {PLAN}: {PLAN_ADDED_ONLY}; {removed} line(s) removed or changed"
                )
        elif not allowed(status, path):
            problems.append(f"{status} {path}: {OUTSIDE}")
        problems += [
            f"{path}: forbidden ({prefix}), which this change may not touch"
            for prefix in forbidden
            if path == prefix or (prefix.endswith("/") and path.startswith(prefix))
        ]
    return problems


CHECKS: dict[str, Callable[[str, str], list[str]]] = {
    "k05": guard_violations,
    "k06": path_violations,
}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in CHECKS:
        sys.stderr.write("usage: python -m tests.support.eko140_guards k05|k06 <base> <head>\n")
        return 2
    try:
        problems = CHECKS[argv[0]](argv[1], argv[2])
    except (CannotJudge, subprocess.CalledProcessError) as exc:
        sys.stderr.write(f"EKO-1-40 {argv[0]}: the check could not run ({exc})\n")
        return 2
    for problem in problems:
        sys.stdout.write(problem + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
