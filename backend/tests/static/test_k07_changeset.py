"""K-07: the change set and the tracked files. Base: $CHANGESET_BASE, else origin/main."""

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support import repo_checks as rc
from tests.support.repo import REPO_ROOT, git

ADR_DIR = "docs/architecture/decisions"
REGISTER = "docs/architecture/architecture-sensitive-paths.md"
UNCHANGED_ADRS = ("ADR-0001-application-stack.md", "ADR-0006-google-calendar.md")
CASES: dict[str, Any] = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "changeset_cases.yaml").read_text(encoding="utf-8")
)
# Present only once this change set is in the base: its rows are then no longer "the change".
EKO_1_06_MARKER = "### 2026-10-28 — ADR-0002-C12 restated"


def merge_base() -> str:
    base = os.environ.get("CHANGESET_BASE") or "origin/main"
    return git("merge-base", base, "HEAD").strip()


def at_base(path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{merge_base()}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else None


def in_worktree(path: str) -> str | None:
    """The file as Git would store it: CRLF from a Windows checkout normalised (`text=auto`)."""
    file = REPO_ROOT / path
    if not file.is_file():
        return None
    return file.read_bytes().decode("utf-8").replace("\r\n", "\n")


def changed_paths() -> list[str]:
    """Both sides of every rename, mode changes included, plus files Git would add."""
    out = git("diff", "--name-status", "-M", merge_base(), "--")
    paths = [p for line in out.splitlines() for p in line.split("\t")[1:]]
    return sorted(set(paths) | set(git("ls-files", "--others", "--exclude-standard").split()))


def is_eko_1_06_change_set() -> bool:
    adr_0002 = at_base(f"{ADR_DIR}/ADR-0002-database-and-migrations.md") or ""
    return EKO_1_06_MARKER not in adr_0002


# Accepted ADR text --------------------------------------------------------------------------


def adr_files_at_base() -> list[str]:
    listed = git("ls-tree", "--name-only", merge_base(), f"{ADR_DIR}/").split()
    return [p for p in listed if p.rsplit("/", 1)[-1].startswith("ADR-")]


def test_k07_adr_files_change_only_by_appended_dated_addenda() -> None:
    problems = []
    for path in adr_files_at_base():
        base, head = at_base(path), in_worktree(path)
        if head is None:
            problems.append(f"{path}: deleted")
        elif base is not None:
            problems += [f"{path}: {p}" for p in rc.adr_append_only(base, head)]
    assert problems == []


def test_k07_adr_0001_and_0006_are_unchanged() -> None:
    if not is_eko_1_06_change_set():
        return
    for name in UNCHANGED_ADRS:
        assert at_base(f"{ADR_DIR}/{name}") == in_worktree(f"{ADR_DIR}/{name}"), name


ADDENDUM = "\n### 2026-10-29 — A later addendum\n\nText.\n"


def test_k07_adr_check_passes_an_appended_dated_addendum() -> None:
    base = "# ADR\n\n## Addenda\n\n### 2026-10-27 — First\n\nAccepted text.\n"
    assert rc.adr_append_only(base, base + ADDENDUM) == []


@pytest.mark.parametrize(
    "edit",
    [
        lambda b: b.replace("Accepted text.", "Accepted words.") + ADDENDUM,
        lambda b: b.replace("Accepted text.\n", "Accepted text. \n"),
        lambda b: b.replace("\n", "\r\n"),
        lambda b: b.replace("### 2026-10-27", ADDENDUM.strip() + "\n\n### 2026-10-27"),
        lambda b: b + "\n## New section\n",
        lambda b: b + "\n### Undated addendum\n",
    ],
    ids=["word", "whitespace", "line-endings", "inserted-between", "new-section", "undated"],
)
def test_k07_adr_check_fails_on_an_edit_of_accepted_text(edit: Any) -> None:
    base = "# ADR\n\n## Addenda\n\n### 2026-10-27 — First\n\nAccepted text.\n"
    assert rc.adr_append_only(base, edit(base)) != []


# docs/prototype/ ----------------------------------------------------------------------------


def test_k07_nothing_under_docs_prototype_changes() -> None:
    assert [p for p in changed_paths() if p.startswith("docs/prototype/")] == []


# The sensitive-paths register ---------------------------------------------------------------


def test_k07_register_changes_only_by_the_two_approved_edits() -> None:
    base, head = at_base(REGISTER), in_worktree(REGISTER)
    assert base is not None and head is not None
    if base == head or not is_eko_1_06_change_set():
        return
    assert rc.register_edits(base, head) == []


def register_variants() -> dict[str, Any]:
    return {
        "compose-row-without-auth": lambda t: t.replace(
            "dependencies, schema, auth, secrets", "dependencies, schema, secrets"
        ),
        "caddyfile-row-dropped": lambda t: "\n".join(
            line for line in t.split("\n") if not line.startswith("| `**/Caddyfile*`")
        ),
        "gitignore-row-dropped": lambda t: "\n".join(
            line for line in t.split("\n") if not line.startswith("| `**/.gitignore`")
        ),
        "class-table-edited": lambda t: t.replace("| yes | no — it is fixed |", "| no | no |"),
        "paragraph-edited": lambda t: t.replace("when in doubt, add it", "when in doubt, skip"),
    }


@pytest.mark.parametrize("variant", sorted(register_variants()))
def test_k07_register_check_fails_on_any_other_edit(variant: str) -> None:
    base, head = at_base(REGISTER), in_worktree(REGISTER)
    assert base is not None and head is not None
    if not is_eko_1_06_change_set():
        return
    changed = register_variants()[variant](head)
    assert changed != head, variant
    assert rc.register_edits(base, changed) != []


# ADR-0004-C9 on tracked files ----------------------------------------------------------------


def test_k07_c9_no_tracked_file_assigns_a_secret(
    repo_files: dict[str, str], secret_inventory: set[str]
) -> None:
    assert rc.secret_assignments(repo_files, secret_inventory) == []


@pytest.mark.parametrize("item", CASES["secret_assignments"], ids=lambda c: c["path"])
def test_k07_c9_fails_on_an_assigned_secret(
    item: dict[str, str], secret_inventory: set[str]
) -> None:
    assert rc.secret_assignments({item["path"]: item["text"]}, secret_inventory) != []


@pytest.mark.parametrize("item", CASES["allowed_references"], ids=lambda c: c["path"])
def test_k07_c9_allows_only_the_required_reference(
    item: dict[str, str], secret_inventory: set[str]
) -> None:
    assert rc.secret_assignments({item["path"]: item["text"]}, secret_inventory) == []


@pytest.mark.parametrize(
    "path", [".env", ".env.example", ".env.local", "backend/.env", "proxy/.env.production"]
)
def test_k07_c9_gitignore_excludes_every_env_file(path: str) -> None:
    ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO_ROOT)
    assert ignored.returncode == 0, path


def test_k07_c9_every_build_context_has_a_dockerignore_excluding_env(
    repo_files: dict[str, str], rendered_dev: dict[str, Any]
) -> None:
    contexts = []
    for service in rendered_dev["services"].values():
        if "build" in service:
            context = os.path.relpath(service["build"]["context"], REPO_ROOT).replace("\\", "/")
            contexts.append("" if context == "." else context)
    assert rc.dockerignore_violations(repo_files, contexts) == []


def test_k07_c9_dockerignore_check_fails_without_the_env_lines() -> None:
    files = {"backend/.dockerignore": ".venv\n.env\n"}
    assert rc.dockerignore_violations(files, ["backend"]) != []
    assert rc.dockerignore_violations({}, ["proxy"]) != []


# Personal data and staff accounts -----------------------------------------------------------


def added_lines() -> dict[str, list[str]]:
    lines: dict[str, list[str]] = {}
    for path in changed_paths():
        text = in_worktree(path)
        if text is None or path in rc.CHECK_FIXTURES:
            continue
        base = at_base(path)
        old = set((base or "").split("\n"))
        lines[path] = [line for line in text.split("\n") if line not in old]
    return lines


def test_k07_no_real_person_data_in_added_lines() -> None:
    assert rc.personal_data(added_lines()) == []


@pytest.mark.parametrize("line", CASES["personal_data"])
def test_k07_personal_data_check_fails_on_a_real_looking_value(line: str) -> None:
    assert rc.personal_data({"x.txt": [line]}) != []


def test_k07_personal_data_check_passes_reserved_domains() -> None:
    lines = ["rep@example.com", "a@eko.test", "b@x.invalid", "c@auth.localhost"]
    assert rc.personal_data({"x.txt": lines}) == []


def test_k07_no_identity_file_holds_users(repo_files: dict[str, str]) -> None:
    assert rc.identity_users(repo_files) == []
    assert rc.identity_users({"identity/realm.json": '{"realm": "eko", "users": []}'}) != []
