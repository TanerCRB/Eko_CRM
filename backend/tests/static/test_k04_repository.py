"""K-04: repository controls. ADR-0002-C12 as restated 2026-10-28, ADR-0003-C3, ADR-0001-C1..C3."""

import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support import repo_checks as rc
from tests.support.image_refs import image_ref_violations, postgres_text_references
from tests.support.repo import REPO_ROOT

FIXTURES = Path(__file__).parent / "fixtures"
Rendered = dict[str, Any]


def reference_cases(verdict: str) -> list[str]:
    lines = (FIXTURES / "image_references.txt").read_text(encoding="utf-8").splitlines()
    return [line.split(" ", 1)[1] for line in lines if line.startswith(verdict + " ")]


def images_of(rendered: Rendered) -> list[str]:
    return [s["image"] for s in rendered["services"].values() if "image" in s]


# ADR-0002-C12 (restated), ADR-0003-C3 ------------------------------------------------------


@pytest.mark.parametrize("reference", reference_cases("accept"))
def test_k04_c12_accepts(reference: str) -> None:
    assert image_ref_violations(reference) == []


@pytest.mark.parametrize("reference", reference_cases("reject"))
def test_k04_c12_rejects(reference: str) -> None:
    assert image_ref_violations(reference) != []


def test_k04_c12_every_postgres_reference_in_tracked_files_is_pinned(
    repo_files: dict[str, str], rendered_dev: Rendered
) -> None:
    assert rc.c12_postgres_references(repo_files, images_of(rendered_dev)) == []


def reference_file_cases(check: str) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = yaml.safe_load(
        (FIXTURES / "reference_files.yaml").read_text(encoding="utf-8")
    )
    return [c for c in cases if c["check"] == check]


@pytest.mark.parametrize("item", reference_file_cases("postgres"), ids=lambda c: c["path"])
def test_k04_c12_finds_references_in_dockerfiles_workflows_and_fixtures(
    item: dict[str, str],
) -> None:
    assert rc.c12_postgres_references({item["path"]: item["text"]}, []) != []


@pytest.mark.parametrize("item", reference_file_cases("postgres-rendered"), ids=lambda c: c["text"])
def test_k04_c12_fails_on_a_rendered_unpinned_postgres(item: dict[str, str]) -> None:
    assert rc.c12_postgres_references({}, [item["text"]]) != []


def test_k04_c12_ignores_connection_strings_and_keys() -> None:
    text = (
        "url: postgres://u@postgres:5432/eko\n"
        "dsn = 'postgresql://postgres/eko'\n"
        "KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak\n"
        "depends_on:\n  postgres:\n    condition: service_healthy\n"
        "KC_DB: postgres\n"
    )
    assert postgres_text_references(text) == []


@pytest.mark.parametrize("path", ["backend/.venv/x.py", "frontend/node_modules/x/package.json"])
def test_k04_c12_reads_only_files_git_would_track(path: str) -> None:
    ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO_ROOT)
    assert ignored.returncode == 0


def test_k04_c12_exclusion_names_files_not_directories() -> None:
    for path in rc.CHECK_FIXTURES:
        assert (REPO_ROOT / path).is_file(), path


def test_k04_adr0003_c3_every_keycloak_reference_is_full_version(
    repo_files: dict[str, str], rendered_dev: Rendered
) -> None:
    assert rc.adr0003_c3_keycloak_references(repo_files, images_of(rendered_dev)) == []


@pytest.mark.parametrize(
    "item",
    reference_file_cases("keycloak") + reference_file_cases("keycloak-rendered"),
    ids=lambda c: c["path"],
)
def test_k04_adr0003_c3_fails_on_a_tag_that_is_not_a_full_version(item: dict[str, str]) -> None:
    if item["check"] == "keycloak-rendered":
        assert rc.adr0003_c3_keycloak_references({}, [item["text"]]) != []
    else:
        assert rc.adr0003_c3_keycloak_references({item["path"]: item["text"]}, []) != []


# ADR-0001-C1 -------------------------------------------------------------------------------


def pyproject() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))


def test_k04_adr0001_c1_pyproject_admits_312_only_with_fastapi_and_pydantic_2() -> None:
    assert rc.adr0001_c1_pyproject(pyproject()) == []


def test_k04_adr0001_c1_uv_lock_is_current() -> None:
    result = subprocess.run(["uv", "lock", "--locked"], cwd=REPO_ROOT / "backend")
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requires-python", ">=3.11"),
        ("requires-python", ">=3.13"),
        ("dependencies", ["pydantic>=2.11,<3"]),
        ("dependencies", ["fastapi>=0.120", "pydantic>=1.10"]),
    ],
)
def test_k04_adr0001_c1_fails_on_a_wrong_manifest(field: str, value: object) -> None:
    manifest = pyproject()
    manifest["project"][field] = value
    assert rc.adr0001_c1_pyproject(manifest) != []


# ADR-0001-C2 and C3 (the frontend's files, delivered by the frontend developer) --------------


def frontend_tsconfigs(repo_files: dict[str, str]) -> dict[str, str]:
    return {
        path: text
        for path, text in repo_files.items()
        if path.startswith("frontend/tsconfig") and path.endswith(".json") and "/" not in path[9:]
    }


def test_k04_adr0001_c2_frontend_manifest_names_react_typescript_vite_and_pnpm(
    repo_files: dict[str, str],
) -> None:
    assert rc.adr0001_c2_frontend(repo_files.get("frontend/package.json"), repo_files) == []


def test_k04_adr0001_c2_fails_on_another_package_managers_lock_file() -> None:
    manifest = '{"packageManager": "pnpm@10.0.0", "dependencies": {"react": "19"},'
    manifest += ' "devDependencies": {"typescript": "5", "vite": "7"}}'
    assert rc.adr0001_c2_frontend(manifest, ["frontend/pnpm-lock.yaml"]) == []
    assert rc.adr0001_c2_frontend(manifest, ["frontend/package-lock.json"]) != []
    assert rc.adr0001_c2_frontend(manifest.replace("pnpm@", "npm@"), []) != []


def test_k04_adr0001_c3_frontend_tsconfigs_are_strict(repo_files: dict[str, str]) -> None:
    assert rc.adr0001_c3_strict(frontend_tsconfigs(repo_files)) == []


def test_k04_adr0001_c3_fails_on_strict_false_even_with_comments() -> None:
    strict = '{\n  // comment\n  "compilerOptions": { /* x */ "strict": true, },\n}\n'
    assert rc.adr0001_c3_strict({"frontend/tsconfig.app.json": strict}) == []
    loose = strict.replace('"strict": true', '"strict": false')
    assert rc.adr0001_c3_strict({"frontend/tsconfig.app.json": loose}) != []
    assert rc.adr0001_c3_strict({"frontend/tsconfig.json": '{"files": []}'}) != []
