"""EKO-1-10 K-07: the change set's own discipline, each check returning its violations."""

import re
import tomllib
from collections.abc import Mapping

DATE = "2026-10-29"
ADDENDUM = re.compile(r"### \d{4}-\d{2}-\d{2} — \S")
# What each ADR's addendum of 2026-10-29 restates (DoD 11): the restatement's own words.
RESTATED = {
    "ADR-0001-application-stack.md": (
        "**ADR-0001-C10 reads:**",
        "**ADR-0001-C13 reads:**",
        "**ADR-0001-C14 reads:**",
        "**ADR-0001-C8 gains a second sentence:**",
        "**ADR-0001-C6 reads:**",
        "**What it states about ADR-0001-C11.**",
    ),
    "ADR-0002-database-and-migrations.md": ("**ADR-0002-C13 reads:**", "**ADR-0002-C4 reads:**"),
    "ADR-0003-identity-and-access.md": ("**ADR-0003-C9 reads:**",),
    "ADR-0004-deployment-and-recovery.md": ("forwarded to EKO-1-15", "**EKO-1-15 (#56)**"),
}
ACCEPTED = f"**Status:** Accepted {DATE}"


def addenda(text: str) -> list[str]:
    """The `###` sections after `## Addenda`, each from its heading to the next."""
    text = text.replace("\r\n", "\n")
    if "\n## Addenda" not in text:
        return []
    tail = text.split("\n## Addenda", 1)[1]
    return ["### " + part for part in re.split(r"(?m)^### ", tail)[1:]]


def restatement_problems(adrs: Mapping[str, str]) -> list[str]:
    """Each restated control is restated in an accepted, dated addendum of 2026-10-29."""
    problems = []
    for name, markers in RESTATED.items():
        text = adrs.get(name)
        if text is None:
            problems.append(f"{name}: missing")
            continue
        sections = [s for s in addenda(text) if s.startswith(f"### {DATE} — ")]
        found = [s for s in sections if all(marker in s for marker in markers)]
        if not found:
            problems.append(f"{name}: no addendum of {DATE} restating {', '.join(markers)}")
        elif not any(ACCEPTED in s for s in found):
            problems.append(f"{name}: the addendum of {DATE} is not accepted")
        for section in addenda(text):
            if not ADDENDUM.match(section):
                problems.append(f"{name}: an undated addendum: {section.splitlines()[0]!r}")
    return problems


REGISTER_ROWS = {
    "`docs/architecture/layer-dependencies.md`": "pipeline",
    "`frontend/env-allowlist.json`": "secrets",
}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_new_row(line: str) -> bool:
    return line.startswith("|") and _cells(line)[0] in REGISTER_ROWS


def register_problems(base: str, head: str) -> list[str]:
    """The register gains exactly the two approved rows (G-2 A, G-14 A); nothing else changes.

    Once both rows are in the base, a later change set is no longer this one: nothing to check.
    """
    base, head = base.replace("\r\n", "\n"), head.replace("\r\n", "\n")
    if all(
        any(line.startswith(f"| {path} |") for line in base.split("\n")) for path in REGISTER_ROWS
    ):
        return []
    problems = []
    added = [line for line in head.split("\n") if _is_new_row(line)]
    for path, risk in REGISTER_ROWS.items():
        rows = [_cells(line) for line in added if _cells(line)[0] == path]
        if len(rows) != 1:
            problems.append(f"row {path}: present {len(rows)} times, not once")
            continue
        cells = rows[0]
        if len(cells) != 4 or cells[1] != risk or not cells[2] or not cells[3]:
            problems.append(f"row {path}: not class {risk} with decisions and a reason")
    rebuilt = "\n".join(line for line in head.split("\n") if not _is_new_row(line))
    if rebuilt != base:
        problems.append("a row other than the two approved ones, or the text around them, changed")
    return problems


COMPARATOR = "backend/tests/support/openapi_compat.py"


def package_names(manifest: str, lock: str) -> tuple[set[str], set[str]]:
    """Declared (dependencies and every dependency group) and locked package names."""
    project = tomllib.loads(manifest)
    declared = [*project["project"]["dependencies"]]
    for group in project.get("dependency-groups", {}).values():
        declared += group
    names = {re.split(r"[\s<>=!~\[;]", spec, maxsplit=1)[0].lower() for spec in declared}
    locked = {package["name"] for package in tomllib.loads(lock).get("package", [])}
    return names, locked


def package_additions(
    base: tuple[str, str], head: tuple[str, str], comparator_in_base: bool
) -> list[str]:
    """K-06: the change set adding the comparator adds no backend package (G-13 A).

    Once the comparator is in the base, a later change set is no longer this one (R-04).
    """
    if comparator_in_base:
        return []
    (declared, locked), (declared_now, locked_now) = package_names(*base), package_names(*head)
    return [f"declared package added: {n}" for n in sorted(declared_now - declared)] + [
        f"locked package added: {n}" for n in sorted(locked_now - locked)
    ]
