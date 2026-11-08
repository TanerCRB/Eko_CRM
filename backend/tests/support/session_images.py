"""EKO-1-19 K-04 (ii): did the runtime session build a project image in place of a checked one?

    python -m tests.support.session_images snapshot --out <file>   # before the session
    python -m tests.support.session_images check --before <file>   # after it

`compose down -v` removes containers and volumes but never images, so a build leaves a trace: an
image name the snapshot did not hold, carrying Compose's project label (every image Compose
builds has it, `localhost/eko-crm/backend:<tag>` included) or named `<project>-<service>`.

Exit codes: 0 = no such image, 1 = one or more (listed on stdout), 2 = Docker could not be read.
"""

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

SERVICES = ("backend", "frontend", "proxy", "backup", "migrate", "worker")
COMPOSE_NAME = re.compile(rf".+-({'|'.join(SERVICES)})")
PROJECT_LABEL = "com.docker.compose.project"
# Planted contrasts built from a shipped image on purpose (lab.py, eko113.py,
# test_k06_frontend_replacement.py); pinned by a static test so the list cannot grow unseen.
EXCEPTIONS = ("localhost/eko-crm/*-variant:*", "localhost/eko-crm/frontend-test:*")


def violations(before: set[str], after: dict[str, dict[str, str]]) -> list[str]:
    """`after` maps each image reference present after the session to its labels."""
    problems = []
    for reference, labels in sorted(after.items()):
        if reference in before or any(fnmatch.fnmatchcase(reference, e) for e in EXCEPTIONS):
            continue
        repository = reference.rsplit(":", 1)[0]
        if PROJECT_LABEL in labels:
            problems.append(f"{reference}: built by Compose for project {labels[PROJECT_LABEL]}")
        elif COMPOSE_NAME.fullmatch(repository):
            problems.append(f"{reference}: named as Compose names a project's built image")
    return problems


def _docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def references() -> set[str]:
    listed = _docker("image", "ls", "--format", "{{.Repository}}:{{.Tag}}").split()
    return {name for name in listed if "<none>" not in name}


def labelled(names: set[str]) -> dict[str, dict[str, str]]:
    found = {}
    for name in sorted(names):
        labels = json.loads(
            _docker("image", "inspect", "--format", "{{json .Config.Labels}}", name)
        )
        found[name] = labels or {}
    return found


def write_snapshot(path: Path, names: set[str]) -> None:
    path.write_text("".join(f"{name}\n" for name in sorted(names)), encoding="utf-8")


def read_snapshot(path: Path) -> set[str]:
    return set(path.read_text(encoding="utf-8").split())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="session_images")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot").add_argument("--out", type=Path, required=True)
    commands.add_parser("check").add_argument("--before", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            write_snapshot(args.out, references())
            return 0
        before = read_snapshot(args.before)
        found = violations(before, labelled(references() - before))
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        sys.stderr.write(f"session_images: cannot tell: {type(error).__name__}\n")
        return 2
    for line in found:
        sys.stdout.write(f"{line}\n")
    sys.stderr.write(f"session_images: {len(found)} image(s) built by the session\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
