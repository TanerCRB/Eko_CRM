"""K-02 *Text* edge (QA, EKO-1-11): when the revision cannot be read, the refusal line names the
error's type only, never the driver's message, which names the host, port, role and sometimes the
URL.

The existing unit tests read from a closed local port. On some hosts libpq reports that as
"connection timeout expired", which names nothing, so a refusal that printed the driver's message
would pass them. Here the driver error carries the text libpq writes when the server answers but
refuses the role, so the configuration values are certainly in the message the refusal must not
repeat.

Contrast (one element changed): the same error's own text does hold those values, so the leak
check can fail on this input.
"""

from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from app.core.settings import Settings, load_settings
from app.data import schema_revision
from app.data.database import database_url
from tests.support.migration_checks import leaked_values
from tests.unit.conftest import SYNTHETIC_PASSWORD

HOST = "db-host-7f3a.internal"
PORT = "6543"
ROLE = "eko_app"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("APP_DB_PASSWORD", SYNTHETIC_PASSWORD)
    for name, value in {
        "APP_DB_HOST": HOST,
        "APP_DB_PORT": PORT,
        "APP_DB_POOL_SIZE": "5",
        "APP_DB_MAX_OVERFLOW": "5",
    }.items():
        monkeypatch.setenv(name, value)
    return load_settings(Settings)


def driver_error(settings: Settings) -> OperationalError:
    url = database_url(settings).render_as_string(hide_password=False)
    message = (
        f'connection to server at "{HOST}", port {PORT} failed: FATAL:  password '
        f'authentication failed for user "{ROLE}" ({url})'
    )
    return OperationalError("SELECT 1", {}, Exception(message))


class RefusingEngine:
    def __init__(self, error: OperationalError) -> None:
        self._error = error

    def connect(self) -> Any:
        raise self._error

    def dispose(self) -> None:
        return None


def values(settings: Settings) -> list[str]:
    return [
        SYNTHETIC_PASSWORD,
        HOST,
        PORT,
        ROLE,
        database_url(settings).render_as_string(hide_password=True),
    ]


@pytest.mark.parametrize("process", ["backend", "worker"])
def test_adr0004_c13_qa_unreadable_revision_refusal_names_no_configuration_value(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, process: str
) -> None:
    error = driver_error(settings)
    monkeypatch.setattr(schema_revision, "create_engine", lambda *a, **kw: RefusingEngine(error))
    with pytest.raises(SystemExit) as stopped:
        schema_revision.refuse_unless_servable(settings, process)
    message = str(stopped.value.code)
    assert leaked_values(message, values(settings)) == []
    assert message.startswith(f"{process} refused to start")
    assert "OperationalError" in message


def test_adr0004_c13_qa_contrast_the_driver_error_itself_names_the_values(
    settings: Settings,
) -> None:
    leaked = leaked_values(str(driver_error(settings)), values(settings))
    assert {SYNTHETIC_PASSWORD, HOST, PORT, ROLE} <= set(leaked)
