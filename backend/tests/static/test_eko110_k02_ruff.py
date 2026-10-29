"""EKO-1-10 K-02: the closed ruff configuration set, its layer bans, TID252 and S608.

Every non-compliant configuration and every fixture module is generated in a temporary directory.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support import layer_table as lt
from tests.support import ruff_config as rc
from tests.support import source_checks as sc

LAYER_DIRS = {
    "domain": "app/domain",
    "services": "app/services",
    "data": "app/data",
    "integrations": "app/integrations",
    "core": "app/core",
    "auth": "app/auth",
    "api": "app/api",
}
NESTED = [f"backend/app/{name}/ruff.toml" for name in LAYER_DIRS if name != "api"]


def backend_dir_rows() -> list[lt.Row]:
    return [
        row
        for row in lt.table_rows()
        if row.glob.startswith("backend/app/") and row.glob.endswith("/**")
    ]


def module_of(layer: str) -> str:
    rows = {row.name: row for row in lt.table_rows()}
    return rows[layer].prefixes[0].split(".", 1)[1]


def configs() -> dict[str, str]:
    return rc.tracked_configs(sc.repository_sources())


def lint(tmp_path: Path, fixtures: dict[str, str]) -> list[rc.Finding]:
    return rc.lint_in_sandbox(tmp_path, configs(), fixtures)


def codes_at(findings: list[rc.Finding], path: str, line: int) -> set[str]:
    return {f.code for f in findings if f.path == path and f.line == line}


def test_eko110_k02_layer_rows_are_the_c11_directories() -> None:
    assert {row.name: row.glob for row in backend_dir_rows()} == {
        name: f"backend/{directory}/**" for name, directory in LAYER_DIRS.items()
    }


def test_eko110_k02_tid251_for_every_forbidden_pair(tmp_path: Path) -> None:
    fixtures = {}
    for row in backend_dir_rows():
        for forbidden in row.forbidden:
            path = f"backend/{LAYER_DIRS[row.name]}/eko110_{row.name}_imports_{forbidden}.py"
            fixtures[path] = f"from app import {module_of(forbidden)}\n"
    assert len(fixtures) == 24, "every (row, forbidden layer) pair of the table has a fixture"
    findings = lint(tmp_path, fixtures)
    assert [p for p in sorted(fixtures) if "TID251" not in codes_at(findings, p, 1)] == []


C11_FOUR_FORMS = (
    "from app import data\nimport app.data\nfrom app.data import x\nimport app.data as d\n"
)


def test_eko110_k02_c11_four_forms_in_domain_none_in_services(tmp_path: Path) -> None:
    domain, services = "backend/app/domain/eko110_c11.py", "backend/app/services/eko110_c11.py"
    findings = lint(tmp_path, {domain: C11_FOUR_FORMS, services: C11_FOUR_FORMS})
    assert [n for n in range(1, 5) if "TID251" not in codes_at(findings, domain, n)] == []
    assert [f for f in findings if f.path == services and f.code == "TID251"] == []


def test_eko110_k02_tid252_in_every_layer(tmp_path: Path) -> None:
    fixtures = {f"backend/{d}/eko110_relative.py": "from . import x\n" for d in LAYER_DIRS.values()}
    absolute = "backend/app/services/eko110_absolute.py"
    findings = lint(tmp_path, {**fixtures, absolute: "from app.services import x\n"})
    assert [p for p in sorted(fixtures) if "TID252" not in codes_at(findings, p, 1)] == []
    assert codes_at(findings, absolute, 1) & {"TID251", "TID252"} == set()


# The closed set (G-11 A) ---------------------------------------------------------------------

COMPLIANT_SERVICES = """extend = "../../pyproject.toml"

[lint.flake8-tidy-imports.banned-api]
"app.api".msg = "services must not depend on api"
"app.auth".msg = "services must not depend on auth"
"""
RUFF_TABLE = '[project]\nname = "x"\n\n[tool.ruff]\nline-length = 120\n'

Change = Callable[[dict[str, str]], dict[str, str]]


def put(path: str, text: str) -> Change:
    return lambda files: {**files, path: text}


def edit(path: str, old: str, new: str) -> Change:
    def apply(files: dict[str, str]) -> dict[str, str]:
        assert old in files[path], (path, old)
        return {**files, path: files[path].replace(old, new)}

    return apply


def drop(path: str) -> Change:
    return lambda files: {p: t for p, t in files.items() if p != path}


SERVICES = "backend/app/services/ruff.toml"
DATA = "backend/app/data/ruff.toml"
FAILING_SETS: dict[str, Change] = {
    "nested-ignores-s608": put(SERVICES, COMPLIANT_SERVICES + '\n[lint]\nignore = ["S608"]\n'),
    "nested-relaxes-relative-imports": put(
        SERVICES,
        COMPLIANT_SERVICES.replace(
            "[lint.flake8-tidy-imports.banned-api]",
            '[lint.flake8-tidy-imports]\nban-relative-imports = "parents"\n\n'
            "[lint.flake8-tidy-imports.banned-api]",
        ),
    ),
    "nested-own-line-length": put(SERVICES, "line-length = 120\n" + COMPLIANT_SERVICES),
    "nested-without-extend": put(
        SERVICES, COMPLIANT_SERVICES.replace('extend = "../../pyproject.toml"\n', "")
    ),
    "nested-extends-other-file": put(
        SERVICES, COMPLIANT_SERVICES.replace("../../pyproject.toml", "../pyproject.toml")
    ),
    "nested-ban-dropped": edit(DATA, '"app.auth".msg', '"app.authx".msg'),
    "nested-ban-added": put(SERVICES, COMPLIANT_SERVICES + '"app.data".msg = "extra"\n'),
    "nested-missing": drop(DATA),
    "compliant-file-in-api": put("backend/app/api/ruff.toml", COMPLIANT_SERVICES),
    "root-pyproject-with-tool-ruff": put("pyproject.toml", RUFF_TABLE),
    "domain-pyproject-with-tool-ruff": put("backend/app/domain/pyproject.toml", RUFF_TABLE),
    "backend-ruff-toml": put("backend/ruff.toml", 'extend = "pyproject.toml"\n'),
    "backend-dot-ruff-toml": put("backend/.ruff.toml", 'extend = "pyproject.toml"\n'),
    "dot-ruff-toml-in-a-layer": put("backend/app/services/.ruff.toml", COMPLIANT_SERVICES),
    "ruff-toml-in-migrations": put(
        "backend/migrations/ruff.toml", 'extend = "../pyproject.toml"\n'
    ),
    "ruff-toml-in-tests": put("backend/tests/ruff.toml", 'extend = "../pyproject.toml"\n'),
    "ruff-toml-in-frontend": put("frontend/ruff.toml", "line-length = 80\n"),
    "nested-deeper-in-a-layer": put("backend/app/services/sub/ruff.toml", COMPLIANT_SERVICES),
    "backend-pyproject-without-tool-ruff": put("backend/pyproject.toml", '[project]\nname = "x"\n'),
    "nested-not-toml": put(SERVICES, "extend = \n"),
}


def test_eko110_k02_ruff_configuration_set_is_closed() -> None:
    files = configs()
    assert sorted(p for p in files if p.endswith("ruff.toml")) == sorted(NESTED)
    assert rc.configuration_violations(files, lt.table_rows()) == []
    assert (
        rc.configuration_violations(
            put("pyproject.toml", '[project]\nname = "x"\n')(files), lt.table_rows()
        )
        == []
    )


@pytest.mark.parametrize("case_id", sorted(FAILING_SETS))
def test_eko110_k02_configuration_check_fails_on_a_generated_set(case_id: str) -> None:
    changed = FAILING_SETS[case_id](configs())
    assert rc.configuration_violations(changed, lt.table_rows()) != [], case_id


# S608 (checklist rule 19) ---------------------------------------------------------------------

QUERIES = {
    "f-string": 'def q(x: str) -> str:\n    return f"SELECT * FROM visits WHERE id = {x}"\n',
    "percent": 'def q(x: str) -> str:\n    return "SELECT * FROM visits WHERE id = %s" % x\n',
    "format": 'def q(x: str) -> str:\n    return "SELECT * FROM visits WHERE id = {}".format(x)\n',
    "concatenation": 'def q(x: str) -> str:\n    return "SELECT * FROM visits WHERE id = " + x\n',
}
BOUND = 'def q() -> str:\n    return "SELECT * FROM visits WHERE id = :id"\n'


def test_eko110_k02_s608_reported_under_backend_app(tmp_path: Path) -> None:
    directories = ["app", *LAYER_DIRS.values()]
    fixtures = {
        f"backend/{d}/eko110_query_{form}.py": text
        for d in directories
        for form, text in QUERIES.items()
    }
    bound = "backend/app/services/eko110_bound.py"
    findings = lint(tmp_path, {**fixtures, bound: BOUND})
    assert [p for p in sorted(fixtures) if "S608" not in codes_at(findings, p, 2)] == []
    assert "S608" not in codes_at(findings, bound, 2)


PYPROJECT = "backend/pyproject.toml"
SWITCHED_OFF: dict[str, Change] = {
    "per-file-app": edit(
        PYPROJECT, '"app/serve.py" = ["S104"]', '"app/serve.py" = ["S104"]\n"app/**" = ["S608"]'
    ),
    "per-file-any": edit(
        PYPROJECT, '"app/serve.py" = ["S104"]', '"app/serve.py" = ["S104", "S608"]'
    ),
    "per-file-prefix": edit(PYPROJECT, '"app/serve.py" = ["S104"]', '"*.py" = ["S6"]'),
    "ignore": edit(PYPROJECT, "[tool.ruff.lint]\n", '[tool.ruff.lint]\nignore = ["S608"]\n'),
    "extend-ignore": edit(
        PYPROJECT, "[tool.ruff.lint]\n", '[tool.ruff.lint]\nextend-ignore = ["S"]\n'
    ),
    "s-not-selected": edit(PYPROJECT, '"TID", "S", "BLE"', '"TID", "BLE"'),
    "nested-ignore": put(SERVICES, COMPLIANT_SERVICES + '\n[lint]\nignore = ["S608"]\n'),
    "nested-select": put(SERVICES, COMPLIANT_SERVICES + '\n[lint]\nselect = ["E"]\n'),
}


def test_eko110_k02_s608_not_switched_off() -> None:
    assert rc.s608_configuration_violations(configs()) == []
    assert sc.s608_noqa(sc.repository_sources()) == []


@pytest.mark.parametrize("case_id", sorted(SWITCHED_OFF))
def test_eko110_k02_s608_check_fails_on_a_configuration_switching_it_off(case_id: str) -> None:
    assert rc.s608_configuration_violations(SWITCHED_OFF[case_id](configs())) != [], case_id


@pytest.mark.parametrize(
    "comment",
    [
        "# noqa: S608",
        "# noqa:S608",
        "# noqa",
        "# NOQA",
        "# noqa: E501, S608",
        "# ruff: noqa",
        "# ruff: noqa: S608",
        "# flake8: noqa",
    ],
)
def test_eko110_k02_s608_inline_noqa_fails(comment: str) -> None:
    line = f'QUERY = "SELECT 1"  {comment}\n'
    assert sc.s608_noqa({"backend/app/services/x.py": line}) != [], comment
    assert sc.s608_noqa({"backend/app/services/fixtures/x.py": line}) != [], comment


def test_eko110_k02_s608_other_noqa_passes() -> None:
    assert sc.s608_noqa({"backend/app/services/x.py": "X = 1  # noqa: E501\n"}) == []
    assert sc.s608_noqa({"backend/tests/x.py": "X = 1  # noqa: S608\n"}) == []
