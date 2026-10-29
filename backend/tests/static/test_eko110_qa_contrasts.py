"""EKO-1-10 QA: contrasts and pins that close what the developer suite left open.

- K-01: the layer-check step itself carries no `if:` (only the job was pinned).
- K-02: ruff run the way CI runs it, `ruff check .` from `backend/`, so a configuration that
  excludes files from discovery (`exclude`, `extend-exclude`, `lint.exclude`) is seen. The other
  K-02 tests name every fixture on the command line, and ruff lints a named file even when the
  configuration excludes it.
- K-04: the helper's own contrasts, judged by every source control at once.
"""

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.static.test_eko110_k01_layers import layer_check_job
from tests.static.test_eko110_k02_ruff import LAYER_DIRS, backend_dir_rows, configs, module_of
from tests.static.test_eko110_k07_changeset import all_source_findings
from tests.support import openapi_compat as oc
from tests.support import ruff_config as rc
from tests.support import source_checks as sc

# K-01 -------------------------------------------------------------------------------------------


def conditions(job: Mapping[str, Any], step: Mapping[str, Any]) -> list[str]:
    return [
        f"{where} has `if: {part['if']}`"
        for where, part in (("job", job), ("step", step))
        if "if" in part
    ]


def test_eko110_qa_k01_layer_check_step_is_unconditional() -> None:
    job, step = layer_check_job()
    assert conditions(job, step) == []
    # Contrast: the same step with one `if:` added is a finding.
    assert conditions(job, {**step, "if": "github.event_name == 'push'"}) != []


# K-02 -------------------------------------------------------------------------------------------

QUERY_AND_RELATIVE = (
    "from . import x\n\n\ndef q(v: str) -> str:\n"
    '    return f"SELECT * FROM visits WHERE id = {v}"\n'
)  # TID252 on line 1, S608 on line 5


def expected_codes() -> dict[tuple[str, int], str]:
    """Every fixture line under backend/app/ and the code CI's ruff run must report there."""
    expected = {}
    for directory in ("app", *LAYER_DIRS.values()):
        path = f"backend/{directory}/eko110_qa_discovered.py"
        expected[(path, 1)] = "TID252"
        expected[(path, 5)] = "S608"
    for row in backend_dir_rows():
        for forbidden in row.forbidden:
            path = f"backend/{LAYER_DIRS[row.name]}/eko110_qa_{row.name}_imports_{forbidden}.py"
            expected[(path, 1)] = "TID251"
    return expected


def fixture_files() -> dict[str, str]:
    files = {}
    for path, line in expected_codes():
        if line == 1 and "_imports_" in path:
            files[path] = f"from app import {module_of(path.rsplit('_imports_', 1)[1][:-3])}\n"
        else:
            files[path] = QUERY_AND_RELATIVE
    return files


def discovered(sandbox: Path, config_files: Mapping[str, str]) -> set[tuple[str, int, str]]:
    """`ruff check .` from backend/, as the CI backend job runs it: ruff discovers the files."""
    for relative, text in {**config_files, **fixture_files()}.items():
        target = sandbox / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    command = [sys.executable, "-m", "ruff", "check", "--no-cache", "--exit-zero"]
    result = subprocess.run(
        [*command, "--output-format", "json", "."],
        cwd=sandbox / "backend",
        capture_output=True,
        text=True,
        check=True,
    )
    root = sandbox.resolve()
    return {
        (
            Path(item["filename"]).resolve().relative_to(root).as_posix(),
            item["location"]["row"],
            item["code"],
        )
        for item in json.loads(result.stdout)
    }


def missing(sandbox: Path, config_files: Mapping[str, str]) -> list[str]:
    found = discovered(sandbox, config_files)
    return sorted(
        f"{path}:{line} {code}"
        for (path, line), code in expected_codes().items()
        if (path, line, code) not in found
    )


def test_eko110_qa_k02_ci_ruff_run_reports_every_ban_tid252_and_s608(tmp_path: Path) -> None:
    assert len(expected_codes()) == 2 * 8 + 24
    assert missing(tmp_path, configs()) == []


ROOT = rc.ROOT_CONFIG
EXCLUDING = {
    "extend-exclude": ("[tool.ruff]\n", '[tool.ruff]\nextend-exclude = ["app/services"]\n'),
    "exclude": ("[tool.ruff]\n", '[tool.ruff]\nexclude = ["services"]\n'),
    "lint-exclude": ("[tool.ruff.lint]\n", '[tool.ruff.lint]\nexclude = ["app/services/*"]\n'),
}


@pytest.mark.parametrize("case_id", sorted(EXCLUDING))
def test_eko110_qa_k02_excluding_a_layer_from_discovery_fails(tmp_path: Path, case_id: str) -> None:
    old, new = EXCLUDING[case_id]
    files = configs()
    assert files[ROOT].count(old) == 1
    gaps = missing(tmp_path, {**files, ROOT: files[ROOT].replace(old, new)})
    assert any(gap.startswith("backend/app/services/") for gap in gaps), case_id


# K-04 -------------------------------------------------------------------------------------------

HELPER = "frontend/src/time/warsaw.ts"
INTL = "const fmt = new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw' });\n"


def test_eko110_qa_k04_helper_iso_and_intl_pass_every_control() -> None:
    assert all_source_findings({HELPER: INTL + "const s = d.toISOString();\n"}) == []


@pytest.mark.parametrize("line", ["const s = d.toTimeString();\n", "const h = d.getHours();\n"])
def test_eko110_qa_k04_helper_device_zone_line_fails(line: str) -> None:
    assert all_source_findings({HELPER: INTL + line}) != []


# Fix round 1 (R-01, R-02, R-03): mechanisms the developer's cases reached only indirectly ------


Schema = dict[str, Any]


def _document(request: Schema, response: Schema, components: Schema | None = None) -> Schema:
    content = "application/json"
    return {
        "openapi": "3.1.0",
        "info": {"title": "qa", "version": "1"},
        "paths": {
            "/api/x": {
                "post": {
                    "requestBody": {"required": True, "content": {content: {"schema": request}}},
                    "responses": {
                        "200": {"description": "ok", "content": {content: {"schema": response}}}
                    },
                }
            }
        },
        "components": {"schemas": components or {}},
    }


INTEGER: Schema = {"type": "integer"}
STRINGS: Schema = {"type": "array", "items": {"type": "string"}}


def _breaks(before: tuple[Schema, Schema], after: tuple[Schema, Schema]) -> bool:
    return oc.breaking_changes(_document(*before), _document(*after)) != []


def test_eko110_qa_k06_request_multiple_of_added_fails_response_passes() -> None:
    stepped = {**INTEGER, "multipleOf": 5}
    assert _breaks((INTEGER, INTEGER), (stepped, INTEGER))
    assert not _breaks((INTEGER, INTEGER), (INTEGER, stepped))


def test_eko110_qa_k06_request_unique_items_added_fails_removed_passes() -> None:
    unique = {**STRINGS, "uniqueItems": True}
    assert _breaks((STRINGS, STRINGS), (unique, STRINGS))
    assert not _breaks((unique, STRINGS), (STRINGS, STRINGS))


def _optional(max_length: int) -> Schema:
    """Pydantic's `str | None = Field(max_length=...)`: the bound sits inside a nullable union."""
    return {"anyOf": [{"type": "string", "maxLength": max_length}, {"type": "null"}]}


def test_eko110_qa_k06_bound_inside_a_nullable_union_is_compared() -> None:
    assert _breaks((_optional(100), INTEGER), (_optional(50), INTEGER))
    assert not _breaks((_optional(100), INTEGER), (_optional(200), INTEGER))


def _ref(name: str) -> Schema:
    return {"$ref": f"#/components/schemas/{name}"}


BRANCHES: Schema = {
    name: {"type": "object", "properties": {"kind": {"const": name.lower()}}}
    for name in ("Field", "Phone", "Email")
}


def test_eko110_qa_k06_request_union_losing_one_of_three_branches_fails() -> None:
    three = {"oneOf": [_ref("Field"), _ref("Phone"), _ref("Email")]}
    two = {"oneOf": [_ref("Field"), _ref("Phone")]}
    previous = _document(three, INTEGER, BRANCHES)
    assert oc.breaking_changes(previous, _document(two, INTEGER, BRANCHES)) != []
    assert oc.breaking_changes(previous, _document(three, INTEGER, BRANCHES)) == []


COMPONENT = "frontend/src/components/Card.tsx"


def test_eko110_qa_k04_escaped_quote_in_a_new_date_argument() -> None:
    one = r"const d = new Date('it\'s, 10:00');" + "\n"
    two = r"const d = new Date('it\'s', 1);" + "\n"
    assert sc.date_apis_outside_helper({COMPONENT: one}) == []
    assert sc.date_apis_outside_helper({COMPONENT: two}) != []


def test_eko110_qa_k02_source_deep_below_a_default_exclusion_fails() -> None:
    assert rc.default_excluded_sources(["backend/app/services/dist/sub/x.py"]) != []
    assert rc.default_excluded_sources(["backend/app/services/distribution/sub/x.py"]) == []
