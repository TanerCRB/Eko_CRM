"""EKO-1-19 K-01: the runtime suite in build mode and in release mode, compared by `pytest -v` log.

    python -m tests.support.mode_parity <build-mode log> <release-mode log>

Both sessions must collect the same non-empty set of node IDs, skip and expect-to-fail the same
ones, and neither may fail or error. A CI job log's timestamp prefix is ignored.

Exit codes: 0 = the two sessions agree, 1 = they differ (listed on stdout), 2 = a log is unreadable.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

OUTCOME = re.compile(
    r"^(?:\S+Z )?(tests/\S+?::\S.*?) (PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)(?: |$)"
)
# The variable and the override are the mode; reading either in a test is a branch on the mode.
MODE_BRANCH = re.compile(r"EKO_CHECKED_IMAGES|checked_images_override\s*\(")


@dataclass
class Session:
    outcomes: dict[str, set[str]] = field(default_factory=dict)

    def having(self, outcome: str) -> set[str]:
        return {node for node, seen in self.outcomes.items() if outcome in seen}


def parse(log: str) -> Session:
    session = Session()
    for line in log.splitlines():
        # `gh run view --log` puts the job and step names before the line, tab-separated.
        match = OUTCOME.match(line.rsplit("\t", 1)[-1].strip())
        if match:
            session.outcomes.setdefault(match.group(1), set()).add(match.group(2))
    return session


def parity_violations(build_log: str, release_log: str) -> list[str]:
    build, release = parse(build_log), parse(release_log)
    problems = []
    if not build.outcomes or not release.outcomes:
        problems.append("a session collected no tests")
    for label, a, b in (
        ("collected", set(build.outcomes), set(release.outcomes)),
        ("skipped", build.having("SKIPPED"), release.having("SKIPPED")),
        ("expected to fail", build.having("XFAIL") | build.having("XPASS"),
         release.having("XFAIL") | release.having("XPASS")),
    ):  # fmt: skip
        problems += [f"{label} in build mode only: {node}" for node in sorted(a - b)]
        problems += [f"{label} in release mode only: {node}" for node in sorted(b - a)]
    for mode, session in (("build", build), ("release", release)):
        problems += [f"{mode} mode failed: {node}" for node in sorted(session.having("FAILED"))]
        problems += [f"{mode} mode error: {node}" for node in sorted(session.having("ERROR"))]
    return problems


def mode_branch_lines(diff: str) -> list[str]:
    """Added lines of a unified diff that read the mode."""
    return [
        line
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++") and MODE_BRANCH.search(line)
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: mode_parity <build-mode log> <release-mode log>\n")
        return 2
    try:
        build, release = (Path(p).read_text(encoding="utf-8", errors="replace") for p in argv)
    except OSError as error:
        sys.stderr.write(f"mode_parity: cannot read a log: {error.strerror}\n")
        return 2
    found = parity_violations(build, release)
    for line in found:
        sys.stdout.write(f"{line}\n")
    for mode, log in (("build", build), ("release", release)):
        session = parse(log)
        counts = {o: len(session.having(o)) for o in ("PASSED", "SKIPPED", "FAILED", "ERROR")}
        sys.stderr.write(f"mode_parity: {mode} mode {len(session.outcomes)} collected {counts}\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
