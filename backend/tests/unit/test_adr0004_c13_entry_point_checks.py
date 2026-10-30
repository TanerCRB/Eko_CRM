"""K-02 unit half: backend and worker check the revision in their main process, after the settings
and before uvicorn or any job; a refusal stops the process naming the process and the reason, never
a host, role, port or password (ADR-0005; the addendum of 2026-10-29, *The descent check*).

The database here is unreachable (a closed local port), so the check cannot read a revision.
"""

import threading
from typing import Any

import pytest
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app import serve, worker
from app.core.settings import Settings, load_settings
from app.data import schema_revision
from app.data.database import database_url
from tests.support.migration_checks import leaked_values
from tests.unit.conftest import SYNTHETIC_PASSWORD, closed_local_port


@pytest.fixture
def unreachable(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("APP_DB_PASSWORD", SYNTHETIC_PASSWORD)
    values = {
        "APP_DB_HOST": "127.0.0.1",
        "APP_DB_PORT": str(closed_local_port()),
        "APP_DB_POOL_SIZE": "5",
        "APP_DB_MAX_OVERFLOW": "5",
        "WEB_CONCURRENCY": "2",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.fixture
def uvicorn_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append({"app": app, **kw}))
    return calls


def configuration_values(values: dict[str, str]) -> list[str]:
    url: URL = database_url(load_settings(Settings))
    return [
        SYNTHETIC_PASSWORD,
        values["APP_DB_HOST"],
        values["APP_DB_PORT"],
        "eko_app",
        url.render_as_string(hide_password=True),
    ]


def test_adr0004_c13_serve_refuses_before_uvicorn_when_the_revision_cannot_be_read(
    unreachable: dict[str, str], uvicorn_calls: list[dict[str, Any]]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        serve.main()
    message = str(stopped.value.code)
    assert uvicorn_calls == []
    assert message.startswith("backend refused to start")
    assert leaked_values(message, configuration_values(unreachable)) == []


def test_adr0004_c13_serve_runs_the_check_after_the_settings_and_before_uvicorn(
    unreachable: dict[str, str],
    uvicorn_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(
        serve, "refuse_unless_servable", lambda settings, process: order.append(process)
    )
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: order.append("uvicorn"))
    serve.main()
    assert order == ["backend", "uvicorn"]
    monkeypatch.delenv("APP_DB_PASSWORD")
    order.clear()
    with pytest.raises(SystemExit) as stopped:
        serve.main()
    assert "APP_DB_PASSWORD" in str(stopped.value.code)
    assert order == []


def test_adr0006_c13_worker_refuses_before_any_job_when_the_revision_cannot_be_read(
    unreachable: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[threading.Event] = []

    def run(stop: threading.Event) -> int:
        ran.append(stop)
        return 0

    monkeypatch.setattr(worker, "run", run)
    with pytest.raises(SystemExit) as stopped:
        worker.main()
    message = str(stopped.value.code)
    assert ran == []
    assert message.startswith("worker refused to start")
    assert leaked_values(message, configuration_values(unreachable)) == []


def test_adr0004_c13_refusal_text_check_finds_a_planted_database_url(
    unreachable: dict[str, str],
) -> None:
    planted = f"backend refused to start: {database_url(load_settings(Settings))}"
    assert leaked_values(planted, configuration_values(unreachable)) != []


def test_adr0004_c13_the_check_opens_one_connection_and_closes_it(
    unreachable: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    disposed: list[bool] = []

    def recording(*args: Any, **kwargs: Any) -> Any:
        engine = create_engine(*args, **kwargs)
        original = engine.dispose

        def dispose() -> None:
            disposed.append(True)
            original()

        monkeypatch.setattr(engine, "dispose", dispose)
        assert kwargs["poolclass"].__name__ == "NullPool"
        return engine

    monkeypatch.setattr(schema_revision, "create_engine", recording)
    with pytest.raises(SystemExit):
        schema_revision.refuse_unless_servable(load_settings(Settings), "backend")
    assert disposed == [True]
