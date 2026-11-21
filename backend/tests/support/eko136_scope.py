"""EKO-1-36 (#214) K-05: the task's code PR only adds files under `backend/tests/` and rows under
`docs/cost-register/` (G-1 A), and changes `docs/PLAN.md` by added lines only (K-05 as amended).
Nothing under `backend/app/`, `backend/migrations/` or `frontend/` changes, and the EKO-1-35 check
and the helpers its gated comparisons use stay byte-identical.

    uv run python -m tests.support.eko136_scope <base-sha> <head-sha>

Judges `git diff base...head` (from the merge base of the two, to head) between two explicit full
SHAs, never the live PR base, origin/main, HEAD or the working tree. A base at a later main that
already holds head gives an empty difference (inert after merge). Renames are not detected, so a
renamed file is its old path deleted. Exit 0 = nothing found, 1 = a finding, 2 = the check could
not run (never read 2 as a pass).
"""

import re
import subprocess
import sys

from tests.support.fixed_pair import require_commit
from tests.support.repo import git

ADDED_ONLY = ("backend/tests/", "docs/cost-register/")
UNTOUCHABLE = ("backend/app/", "backend/migrations/", "frontend/")
FROZEN = (
    "backend/tests/support/frontend_contract.py",
    "backend/tests/static/test_eko135_k05_contract_unchanged.py",
    "backend/tests/static/test_eko135_k06_rule7_untouched.py",
    "backend/tests/static/test_eko135_k07_runtime_dependencies.py",
    "backend/tests/static/test_k07_changeset.py",
    "backend/tests/support/contract_tree.py",
    "backend/tests/support/fixed_pair.py",
)
FULL_SHA = re.compile(r"[0-9a-f]{40}")
NOT_ADDED = "only added files under backend/tests/ and docs/cost-register/ may change"
# K-05 as amended in the Issue (option A): the step-2 plan reservation, added lines only.
PLAN = "docs/PLAN.md"
PLAN_ADDED_ONLY = "may change by added lines only"
REMOVED = "removed or modified"


class CannotJudge(Exception):
    """The pair cannot be judged: never a pass."""


def commit(sha: str) -> str:
    if not FULL_SHA.fullmatch(sha):
        raise CannotJudge(f"{sha!r} is not a full 40-character SHA")
    if require_commit(sha) != sha:
        raise CannotJudge(f"{sha} is not a commit")
    return sha


def tree_entry(at: str, path: str) -> str:
    """Mode, object id and path of `path` at `at`; empty when `at` holds no such file."""
    return git("ls-tree", at, "--", path)


def removed_lines(base: str, head: str, path: str) -> int:
    """Lines of `path` removed or modified in `base...head`; a binary diff counts as one."""
    numstat = git("diff", "--numstat", "--no-renames", f"{base}...{head}", "--", path).split("\t")
    return int(numstat[1]) if numstat[1].isdigit() else 1


def scope_violations(base: str, head: str) -> list[str]:
    base, head = commit(base), commit(head)
    merge = git("merge-base", base, head).strip()
    fields = git("diff", "--name-status", "--no-renames", "-z", f"{base}...{head}").split("\0")
    problems = []
    for status, path in zip(fields[0:-1:2], fields[1::2], strict=True):
        if status == "M" and path == PLAN:
            removed = removed_lines(base, head, path)
            if removed:
                problems.append(f"M {PLAN}: {PLAN_ADDED_ONLY}; {removed} line(s) {REMOVED}")
        elif status != "A" or not path.startswith(ADDED_ONLY):
            problems.append(f"{status} {path}: {NOT_ADDED}")
        problems += [
            f"{path}: under {prefix}, which this change may not touch"
            for prefix in UNTOUCHABLE
            if path.startswith(prefix)
        ]
    problems += [
        f"{path}: not byte-identical to the base"
        for path in FROZEN
        if tree_entry(head, path) != tree_entry(merge, path)
    ]
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -m tests.support.eko136_scope <base-sha> <head-sha>\n")
        return 2
    try:
        problems = scope_violations(argv[0], argv[1])
    except (CannotJudge, subprocess.CalledProcessError) as exc:
        sys.stderr.write(f"EKO-1-36 scope: the check could not run ({exc})\n")
        return 2
    for problem in problems:
        sys.stdout.write(problem + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
