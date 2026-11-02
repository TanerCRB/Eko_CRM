"""EKO-1-13 K-04 (unit half): an unhandled exception in a request leaves in `backend`'s output
only its type, code location and the correlation identifier, and the 500 body holds neither
message nor marker (ADR-0005 addendum 2026-11-02).

The fixture app is `create_app()` with test-only routes, under the repository's own process
logging (`install_process_logging`): a fixture wiring its own handlers would prove the fixture.
`test_…_create_app_installs_the_request_handling` shows the shipped factory uses the same entry.
Contrast: the same route under a formatter that writes the record's message and traceback (one
element changed) puts the marker in the output, so the leak check can fail.
"""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main
from app.data.database import Database
from app.main import create_app
from tests.support import log_lines as ll
from tests.support.fixture_app import (
    FORBIDDEN,
    FORBIDDEN_TEXT,
    add_fixture_routes,
    install_for_test,
)
from tests.support.fixture_app import restored_process_state as restored

Output = Callable[[], str]


@pytest.fixture
def output(capfd: pytest.CaptureFixture[str]) -> Iterator[Output]:

    with restored():
        install_for_test("backend")
        capfd.readouterr()
        yield lambda: capfd.readouterr().err


@pytest.fixture
def app(backend_env: None) -> FastAPI:
    return add_fixture_routes(create_app())


def call(app: FastAPI, path: str) -> tuple[int, str, str]:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(path)
    return response.status_code, response.text, response.headers.get("eko-correlation-id", "")


# path -> (error type, cause type or None)
ERROR_CASES: dict[str, tuple[str, str | None]] = {
    "/api/fixture/boom": ("builtins.RuntimeError", "builtins.ValueError"),
    "/api/fixture/driver": ("sqlalchemy.exc.OperationalError", "sqlalchemy.exc.IntegrityError"),
    "/api/fixture/group": ("builtins.ExceptionGroup", None),
    "/api/fixture/long": ("builtins.RuntimeError", None),
    "/api/fixture/middleware-boom": ("builtins.RuntimeError", None),
}


@pytest.mark.parametrize("path", sorted(ERROR_CASES))
def test_adr0005_backend_error_handling_writes_type_and_location_only(
    app: FastAPI, output: Output, path: str
) -> None:
    status, body, cid = call(app, path)
    text = output()
    assert status == 500
    assert body == "Internal Server Error"
    lines, others = ll.json_lines(text)
    assert others == [], others
    errors = [line for line in lines if line["event"] == "error"]
    assert len(errors) == 1, lines
    [error] = errors
    expected_type, expected_cause = ERROR_CASES[path]
    assert error["error"] == expected_type
    assert error.get("cause") == expected_cause
    assert error["correlation_id"] == cid
    assert ll.app_line_problems(error) == []
    # The innermost frame of the application's own code: the request handling in app.main.
    assert error["at"].startswith("app."), error
    assert ll.leaks(text + body, *FORBIDDEN, *FORBIDDEN_TEXT) == []


def test_adr0005_backend_error_handling_third_party_record_with_exc_info(
    app: FastAPI, output: Output
) -> None:
    """A library logger's record carrying an exception (the pool invalidating a connection)."""
    status, _, cid = call(app, "/api/fixture/pool")
    text = output()
    assert status == 200
    lines, _ = ll.json_lines(text)
    [pool] = [line for line in lines if line["logger"].startswith("sqlalchemy.pool")]
    assert pool["event"] == "error"
    assert pool["error"] == "sqlalchemy.exc.IntegrityError"
    assert pool["correlation_id"] == cid
    assert ll.leaks(text, *FORBIDDEN, *FORBIDDEN_TEXT) == []


def test_adr0005_backend_error_handling_exception_as_log_argument(output: Output) -> None:
    """An exception passed as a message argument, as uvicorn's factory-load record does."""
    try:
        raise TypeError(f"argument {FORBIDDEN[0]}")
    except TypeError as exc:
        logging.getLogger("uvicorn.error").error("Error loading ASGI app factory: %s", exc)
        logging.getLogger("app.fixture").error("app record %s", exc)
    text = output()
    lines, _ = ll.json_lines(text)
    assert [line["event"] for line in lines] == ["error", "error"], lines
    assert {line["error"] for line in lines} == {"builtins.TypeError"}
    assert ll.leaks(text, *FORBIDDEN) == []


def test_adr0005_backend_error_handling_create_app_installs_the_request_handling(
    backend_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[FastAPI] = []
    real = main.install_request_handling

    def spy(target: FastAPI) -> None:
        calls.append(target)
        real(target)

    monkeypatch.setattr(main, "install_request_handling", spy)
    built = create_app()
    assert calls == [built]


def test_adr0005_backend_error_handling_create_app_failure_is_type_and_location(
    backend_env: None, output: Output, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0005 amendment (S-2): a failure building the app writes the error line and exits 1."""

    def broken(settings: Any) -> Any:
        raise RuntimeError(f"cannot build {FORBIDDEN[0]}")

    monkeypatch.setattr(Database, "from_settings", broken)
    with pytest.raises(SystemExit) as stopped:
        create_app()
    assert stopped.value.code == 1
    text = output()
    lines, others = ll.json_lines(text)
    assert others == []
    [line] = lines
    assert (line["event"], line["error"]) == ("error", "builtins.RuntimeError")
    assert line["at"].startswith("app.main:create_app:"), line
    assert "correlation_id" not in line
    assert ll.leaks(text, *FORBIDDEN) == []


def test_adr0005_backend_error_handling_contrast_message_formatter_leaks(
    app: FastAPI, output: Output
) -> None:
    """Planted: the same route, with the root handler's formatter writing message and traceback."""
    for handler in logging.getLogger().handlers:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    call(app, "/api/fixture/boom")
    text = output()
    assert "Traceback" in text
    assert ll.leaks(text, *FORBIDDEN) != []
