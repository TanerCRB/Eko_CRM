"""EKO-3-06, ADR-0005-C22, backend half (A-3 A): the synthetic-only declaration is read only in
`backend/app/core/settings.py`, as a plain string, and only the one exact value declares it.
Absent, empty, whitespace only, a case or whitespace variant and every boolean word are "not
declared". The composition half (the variable reaches `worker` as written) is
`tests/static/test_eko306_c22_declaration_carrier.py`.
"""

import pytest

from app.core.settings import SeedSettings
from tests.static.test_eko301_adr0003_c35_owned_tables_scoped import app_sources

VARIABLE = "APP_SYNTHETIC_DATA_ONLY"
SETTINGS = "backend/app/core/settings.py"
NOT_DECLARED = ["", " ", "\t", "Declared", "DECLARED", " declared", "declared ", "true", "1", "yes"]
NOT_DECLARED += ["false", "0", "on", "declared\n", "synthetic"]


@pytest.fixture
def database_values(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-eko306-app")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "2")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "0")
    monkeypatch.delenv(VARIABLE, raising=False)
    return monkeypatch


def test_c22_the_accepted_value_declares(database_values: pytest.MonkeyPatch) -> None:
    database_values.setenv(VARIABLE, "declared")
    assert SeedSettings().declares_synthetic_data_only() is True


def test_c22_an_absent_variable_does_not_declare(database_values: pytest.MonkeyPatch) -> None:
    assert SeedSettings().declares_synthetic_data_only() is False


@pytest.mark.parametrize("value", NOT_DECLARED)
def test_c22_any_other_value_does_not_declare(
    database_values: pytest.MonkeyPatch, value: str
) -> None:
    database_values.setenv(VARIABLE, value)
    assert SeedSettings().declares_synthetic_data_only() is False


def readers(sources: dict[str, str]) -> list[str]:
    return sorted(
        path
        for path, text in sources.items()
        if path.startswith("backend/app/") and VARIABLE.lower() in text.lower() and path != SETTINGS
    )


def test_c22_no_file_under_app_but_settings_names_the_variable() -> None:
    sources = app_sources()
    assert VARIABLE.lower() in sources[SETTINGS].lower()
    assert readers(sources) == []


def test_c22_contrast_a_planted_reader_elsewhere_is_found() -> None:
    planted = {"backend/app/seed.py": 'import os\nos.environ.get("APP_SYNTHETIC_DATA_ONLY")\n'}
    assert readers(planted) == ["backend/app/seed.py"]
    lower = {"backend/app/data/x.py": "getenv('app_synthetic_data_only')\n"}
    assert readers(lower) == ["backend/app/data/x.py"]
