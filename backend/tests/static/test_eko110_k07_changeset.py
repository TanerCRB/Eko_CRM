"""EKO-1-10 K-07: restatements as dated addenda, the two register rows, and no exclusion.

EKO-1-06's change-set tests (test_k07_changeset.py) run on this change set unchanged.
"""

import json
from collections.abc import Callable

import pytest

from tests.static.test_k07_changeset import at_base, in_worktree
from tests.support import changeset_checks as cc
from tests.support import layer_table as lt
from tests.support import repo_checks as rc
from tests.support import source_checks as sc
from tests.support.repo import REPO_ROOT

ADR_DIR = "docs/architecture/decisions"
ADRS = (
    "ADR-0001-application-stack.md",
    "ADR-0002-database-and-migrations.md",
    "ADR-0003-identity-and-access.md",
    "ADR-0004-deployment-and-recovery.md",
)
REGISTER = "docs/architecture/architecture-sensitive-paths.md"


def adr_texts() -> dict[str, str]:
    texts = {name: in_worktree(f"{ADR_DIR}/{name}") for name in ADRS}
    assert None not in texts.values()
    return {name: text for name, text in texts.items() if text is not None}


def test_eko110_k07_each_restated_control_has_a_dated_addendum() -> None:
    assert cc.restatement_problems(adr_texts()) == []


ADR_1, ADR_2, ADR_4 = ADRS[0], ADRS[1], ADRS[3]
Edit = Callable[[dict[str, str]], dict[str, str]]


def replace(name: str, old: str, new: str) -> Edit:
    def apply(texts: dict[str, str]) -> dict[str, str]:
        assert old in texts[name], (name, old)
        return {**texts, name: texts[name].replace(old, new)}

    return apply


def move_into_controls(texts: dict[str, str]) -> dict[str, str]:
    """The same restatement made by editing the control's row, not as an addendum."""
    text = texts[ADR_2]
    marker = "- **ADR-0002-C4 reads:**"
    start = text.index(marker)
    end = text.index("\n\n", start)
    moved = text[:start] + text[end:]
    return {**texts, ADR_2: moved.replace("## Controls", "## Controls\n\n" + text[start:end], 1)}


MISSING: dict[str, Edit] = {
    "c10-dropped": replace(ADR_1, "**ADR-0001-C10 reads:**", "**C10:**"),
    "c11-scope-dropped": replace(ADR_1, "**What it states about ADR-0001-C11.**", "**Scope.**"),
    "c4-dropped": replace(ADR_2, "**ADR-0002-C4 reads:**", "**C4:**"),
    "c4-in-the-controls-row": move_into_controls,
    "c9-dropped": replace(ADRS[2], "**ADR-0003-C9 reads:**", "**C9:**"),
    "forwards-dropped": replace(ADR_4, "forwarded to EKO-1-15", "forwarded"),
    "undated": replace(ADR_1, "### 2026-10-29 — ADR-0001-C6", "### Undated — ADR-0001-C6"),
    "not-accepted": replace(ADR_2, "**Status:** Accepted 2026-10-29", "**Status:** Draft"),
}


@pytest.mark.parametrize("case_id", sorted(MISSING))
def test_eko110_k07_restatement_check_fails_on_a_missing_addendum(case_id: str) -> None:
    assert cc.restatement_problems(MISSING[case_id](adr_texts())) != [], case_id


# The sensitive-paths register (G-2 A, G-14 A) --------------------------------------------------


def register_texts() -> tuple[str, str]:
    base, head = at_base(REGISTER), in_worktree(REGISTER)
    assert base is not None and head is not None
    return base, head


def test_eko110_k07_sensitive_paths_register_adds_only_the_two_rows() -> None:
    base, head = register_texts()
    assert cc.register_problems(base, head) == []


def drop_row(path: str) -> Callable[[str], str]:
    return lambda t: "\n".join(line for line in t.split("\n") if not line.startswith(f"| `{path}`"))


REGISTER_EDITS: dict[str, Callable[[str], str]] = {
    "layer-table-row-dropped": drop_row("docs/architecture/layer-dependencies.md"),
    "allow-list-row-dropped": drop_row("frontend/env-allowlist.json"),
    "layer-table-class-changed": lambda t: t.replace(
        "| `docs/architecture/layer-dependencies.md` | pipeline |",
        "| `docs/architecture/layer-dependencies.md` | model |",
    ),
    "allow-list-class-dropped": lambda t: t.replace(
        "| `frontend/env-allowlist.json` | secrets |", "| `frontend/env-allowlist.json` | |"
    ),
    "other-row-edited": lambda t: t.replace(
        "| `frontend/vite.config.*` | secrets |", "| `frontend/vite.config.*` | dependencies |"
    ),
    "other-row-dropped": drop_row("scripts/**"),
    "third-row-added": lambda t: t.replace(
        "| `scripts/**` |", "| `tools/**` | pipeline | — | x |\n| `scripts/**` |"
    ),
    "class-table-edited": lambda t: t.replace("| yes | no — it is fixed |", "| no | no |"),
}


@pytest.mark.parametrize("case_id", sorted(REGISTER_EDITS))
def test_eko110_k07_register_check_fails_on_any_other_edit(case_id: str) -> None:
    base, head = register_texts()
    edited = REGISTER_EDITS[case_id](head)
    assert edited != head, case_id
    assert cc.register_problems(base, edited) != [], case_id


# No control passes because of an exclusion ----------------------------------------------------


def allow_list() -> frozenset[str]:
    path = REPO_ROOT / "frontend" / "env-allowlist.json"
    # A missing allow-list admits nothing here; its own test (K-04) requires the file.
    return (
        frozenset(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else frozenset()
    )


def all_source_findings(files: sc.Files) -> list[str]:
    rows = lt.table_rows()
    worker = "backend/app/worker.py"
    return [
        *sc.c12_tokens(files),
        *sc.env_reads(files),
        *sc.clock_reads(files),
        *sc.sqlalchemy_outside_data(files),
        *sc.schema_creation(files),
        *sc.password_columns(files),
        *sc.s608_noqa(files),
        *sc.email_senders(files),
        *sc.device_zone_reads(files),
        *sc.to_json(files),
        *sc.date_apis_outside_helper(files),
        *sc.client_storage(files),
        *sc.frontend_env_reads(files, allow_list()),
        *sc.vite_env_injection(files),
        *sc.cross_tree_references(files),
        *(lt.whole_file_findings(worker, files[worker], rows) if worker in files else []),
    ]


# One violation per control, planted where an exclusion would hide it.
BAIT_DIRECTORIES = ("fixtures/", "tests/", "test/", "__fixtures__/", "testdata/")
PLANTS: dict[str, tuple[Callable[[sc.Files], list[str]], str, str]] = {
    "c12": (sc.c12_tokens, "backend/app/services/", "jwt = 1\n"),
    "env": (sc.env_reads, "backend/app/services/", "import os\nX = os.environ\n"),
    "clock": (sc.clock_reads, "backend/app/services/", "import time\nX = time.time()\n"),
    "clock-migrations": (sc.clock_reads, "backend/migrations/", 'X = "CURRENT_DATE"\n'),
    "sqlalchemy": (sc.sqlalchemy_outside_data, "backend/app/services/", "import sqlalchemy\n"),
    "schema": (sc.schema_creation, "backend/migrations/", "metadata.create_all(engine)\n"),
    "password": (sc.password_columns, "backend/migrations/", 'sa.Column("password")\n'),
    "noqa": (sc.s608_noqa, "backend/app/services/", "X = 1  # noqa\n"),
    "email": (sc.email_senders, "backend/app/services/", "import smtplib\n"),
    "device-zone": (sc.device_zone_reads, "frontend/src/", "d.getHours();\n"),
    "to-json": (sc.to_json, "frontend/src/", "d.toJSON();\n"),
    "date-api": (sc.date_apis_outside_helper, "frontend/src/", "Date.now();\n"),
    "storage": (sc.client_storage, "frontend/src/", "localStorage.clear();\n"),
    "env-frontend": (
        lambda f: sc.frontend_env_reads(f, frozenset()),
        "frontend/src/",
        "import.meta.env.VITE_X;\n",
    ),
    "rule-7": (sc.cross_tree_references, "frontend/src/", 'import x from "../../backend/x";\n'),
}


def test_eko110_k07_no_violating_file_under_scanned_trees() -> None:
    assert all_source_findings(sc.repository_sources()) == []


@pytest.mark.parametrize("control", sorted(PLANTS))
@pytest.mark.parametrize("bait", BAIT_DIRECTORIES)
def test_eko110_k07_a_control_excludes_no_directory(control: str, bait: str) -> None:
    check, tree, text = PLANTS[control]
    for name in ("x.py", "test_x.py", "conftest.py", "x.test.ts", "x.fixture.ts"):
        assert check({f"{tree}{bait}{name}": text}) != [], (control, bait, name)


def test_eko110_k07_secret_check_excludes_no_fixture(secret_inventory: set[str]) -> None:
    name = "APP_DB_PASSWORD"
    named = f'("{name}", "synthetic-openapi-only")\n'
    # Assembled at test time: no tracked file holds the assignment (EKO-1-06 K-07 reads them all).
    assigned = name + ": " + "synthetic-but-assigned\n"
    for path in ("backend/tests/static/fixtures/eko110_cases.yaml", "backend/tests/support/x.py"):
        assert rc.secret_assignments({path: named}, secret_inventory) == [], path
        assert rc.secret_assignments({path: assigned}, secret_inventory) != [], path
