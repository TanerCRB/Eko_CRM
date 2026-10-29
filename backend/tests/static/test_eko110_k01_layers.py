"""EKO-1-10 K-01: the layer check against the PR's base, worker.py's imports, ADR-0003-C12."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support import layer_table as lt
from tests.support import source_checks as sc
from tests.support import workflow_checks as wc
from tests.support.git_sandbox import Sandbox
from tests.support.repo import REPO_ROOT

CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WORKER = "backend/app/worker.py"
BASE_EXPR = "${{ github.event.pull_request.base.sha || github.event.before }}"
HEAD_EXPR = "${{ github.event.pull_request.head.sha || github.sha }}"
MISSING_COMMIT = "1" * 40


def layer_check_job() -> tuple[dict[str, Any], dict[str, Any]]:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    found = [
        (job, step)
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "scripts/layer-check.sh" in str(step.get("run", ""))
    ]
    assert len(found) == 1, "exactly one ci.yml step runs scripts/layer-check.sh"
    return found[0]


@pytest.fixture
def frontend_sandbox(tmp_path: Path) -> tuple[Sandbox, str]:
    box = Sandbox(tmp_path)
    base = box.commit(
        {
            "frontend/src/components/Card.tsx": "export const Card = 1;\n",
            "frontend/src/features/Home.tsx": "export const Home = 1;\n",
            "README.md": "sandbox\n",
        },
        "base",
    )
    return box, base


FORBIDDEN_FRONTEND_IMPORT = 'import { x } from "@/api/client";'


def test_eko110_k01_ci_layer_check_compares_the_pr_base(
    frontend_sandbox: tuple[Sandbox, str],
) -> None:
    job, step = layer_check_job()
    assert "if" not in job, "the layer check runs on every PR and push"
    checkout = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert checkout and (checkout[0].get("with") or {}).get("fetch-depth") == 0
    assert step.get("env") == {"BASE": BASE_EXPR, "HEAD": HEAD_EXPR}
    assert wc.failures_fail_the_run({"jobs": {"layers": job}}) == []

    box, base = frontend_sandbox
    # Directory contrast: the same import is allowed in features/ and forbidden in components/.
    allowed = box.commit(box.append("frontend/src/features/Home.tsx", FORBIDDEN_FRONTEND_IMPORT))
    result = box.run(step["run"], {"BASE": base, "HEAD": allowed})
    assert result.returncode == 0 and "clean" in result.stdout, result.stdout + result.stderr

    violation = box.commit(
        box.append("frontend/src/components/Card.tsx", FORBIDDEN_FRONTEND_IMPORT)
    )
    result = box.run(step["run"], {"BASE": base, "HEAD": violation})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "frontend/src/components/Card.tsx" in result.stderr

    # A push to main: the range is the pushed commits, the violation is not in the last one.
    later = box.commit({"README.md": "sandbox, later\n"})
    result = box.run(step["run"], {"BASE": base, "HEAD": later})
    assert result.returncode == 1, result.stdout + result.stderr


def test_eko110_k01_ci_layer_check_verdict_without_either_tree(
    frontend_sandbox: tuple[Sandbox, str],
) -> None:
    _, step = layer_check_job()
    box, base = frontend_sandbox
    head = box.commit({"README.md": "sandbox, docs only\n"})
    result = box.run(step["run"], {"BASE": base, "HEAD": head})
    assert result.returncode == 0 and "clean" in result.stdout, result.stdout + result.stderr


def test_eko110_k01_ci_layer_check_base_missing_from_the_checkout_is_red(
    frontend_sandbox: tuple[Sandbox, str],
) -> None:
    _, step = layer_check_job()
    box, _ = frontend_sandbox
    head = box.commit({"README.md": "sandbox, shallow\n"})
    result = box.run(step["run"], {"BASE": MISSING_COMMIT, "HEAD": head})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "clean" not in result.stdout


# The worker row in the layer check ---------------------------------------------------------


@pytest.fixture
def backend_sandbox(tmp_path: Path) -> tuple[Sandbox, str]:
    box = Sandbox(tmp_path)
    base = box.commit(
        {
            WORKER: '"""Worker."""\n\nimport logging\n',
            "backend/app/main.py": '"""Main."""\n\nimport logging\n',
        },
        "base",
    )
    return box, base


@pytest.mark.parametrize(
    ("path", "line", "expected"),
    [
        (WORKER, "from app.api.health import router", 1),
        (WORKER, "import app.auth as a", 1),
        (WORKER, "from app.auth.session import current_user", 1),
        (WORKER, "from app.core.settings import Settings", 0),
        ("backend/app/main.py", "from app.api.health import router", 0),
    ],
)
def test_eko110_k01_layer_check_flags_worker_importing_api_or_auth(
    backend_sandbox: tuple[Sandbox, str], path: str, line: str, expected: int
) -> None:
    box, base = backend_sandbox
    head = box.commit(box.append(path, line))
    result = box.run(f'bash scripts/layer-check.sh "{base}" "{head}"', {})
    assert result.returncode == expected, result.stdout + result.stderr
    if expected:
        assert "worker must not depend on" in result.stderr


# The whole of worker.py against its row (G-8 A) --------------------------------------------


def worker_row() -> lt.Row:
    rows = [row for row in lt.table_rows() if row.name == "worker"]
    assert len(rows) == 1, "one worker row in docs/architecture/layer-dependencies.md"
    return rows[0]


def test_eko110_k01_worker_path_under_two_rows_fails() -> None:
    # As layer-check.sh exits 2 on the same ambiguity: never "no row, nothing to judge".
    rows = [*lt.table_rows(), lt.Row("entry", "backend/app/*.py", (), ("api",))]
    assert lt.whole_file_findings(WORKER, "import logging\n", rows) != []
    assert [row.name for row in lt.table_rows() if row.matches(WORKER)] == ["worker"]


def test_eko110_k01_worker_imports_judged_against_its_row() -> None:
    row = worker_row()
    assert row.matches(WORKER) and (REPO_ROOT / WORKER).is_file()
    source = (REPO_ROOT / WORKER).read_text(encoding="utf-8")
    assert lt.whole_file_findings(WORKER, source, lt.table_rows()) == []


WORKER_VIOLATIONS = {
    "from-app-import-api": ("from app import api\n", 1),
    "parenthesised-later-line": ("from app import (\n    core,\n    api,\n)\n", 3),
    "import-dotted": ("import app.api\n", 1),
    "import-as": ("import app.auth as a\n", 1),
    "from-submodule": ("from app.api.health import router\n", 1),
    "indented-in-function": ("def f() -> None:\n    from app.auth import session\n", 2),
    "type-checking": (
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from app.api import health\n",
        4,
    ),
    "relative": ("from . import auth\n", 1),
    "crlf": ("import logging\r\nfrom app import api\r\n", 2),
}


@pytest.mark.parametrize("case_id", sorted(WORKER_VIOLATIONS))
def test_eko110_k01_worker_check_fails_on_a_fixture(case_id: str) -> None:
    source, line = WORKER_VIOLATIONS[case_id]
    findings = lt.whole_file_findings(WORKER, source, lt.table_rows())
    assert len(findings) == 1, findings
    assert f"{WORKER}:{line}:" in findings[0]


@pytest.mark.parametrize(
    ("path", "source"),
    [
        (WORKER, "from app import core\n"),
        (WORKER, "from app.core.settings import Settings, load_settings\n"),
        (WORKER, "import logging\nimport app.core.settings\n"),
        ("backend/app/main.py", "from app.api.health import router\n"),
    ],
)
def test_eko110_k01_worker_check_contrasts_pass(path: str, source: str) -> None:
    assert lt.whole_file_findings(path, source, lt.table_rows()) == []


def test_eko110_k01_unchanged_forbidden_line_is_caught_only_by_the_worker_test(
    backend_sandbox: tuple[Sandbox, str],
) -> None:
    box, _ = backend_sandbox
    planted = box.commit(box.append(WORKER, "from app.api.health import router"))
    head = box.commit(box.append(WORKER, "import sys"))
    result = box.run(f'bash scripts/layer-check.sh "{planted}" "{head}"', {})
    assert result.returncode == 0, result.stdout + result.stderr
    source = (box.root / WORKER).read_text(encoding="utf-8")
    assert lt.whole_file_findings(WORKER, source, lt.table_rows()) != []


# ADR-0003-C12: no token handling in services/ or domain/ -------------------------------------


def test_eko110_k01_c12_token_grep_fails_on_a_fixture() -> None:
    assert sc.c12_tokens(sc.repository_sources()) == []
    for directory in ("services", "domain"):
        for token in ("jwt", "jose", "id_token", "access_token", "JWT", "ID_TOKEN"):
            fixture = {f"backend/app/{directory}/x.py": f"# reads the {token}\n"}
            assert sc.c12_tokens(fixture) != [], (directory, token)
    assert sc.c12_tokens({"backend/app/services/fixtures/x.py": "jwt = 1\n"}) != []
    assert sc.c12_tokens({"backend/app/api/x.py": "access_token = 1\n"}) == []
    assert sc.c12_tokens({"backend/app/services_extra/x.py": "jwt = 1\n"}) == []
