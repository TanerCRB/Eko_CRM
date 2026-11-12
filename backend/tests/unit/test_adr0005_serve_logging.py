"""EKO-1-13 K-03 mutations (6) and (8), which no runtime case can see on this image.

- (6) Uvicorn's access log back on: under the shipped `log_config` its logger is below its level
  and its line would be a format string, so the runtime output stays clean. The argument itself is
  therefore pinned here: `serve.main` passes `access_log=False` and the repository's `log_config`.
- (8) A third-party logger's arguments interpolated: the image ships no WebSocket library, so
  uvicorn never writes the WebSocket line whose argument is the path with its query. Here a record
  of that form on `uvicorn.error` must come out as its format string.
"""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import uvicorn

from app import serve
from app.core.logs import log_config
from tests.support import log_lines as ll
from tests.support.fixture_app import MARKER, install_for_test
from tests.support.fixture_app import restored_process_state as restored


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append({"app": app, **kw}))
    monkeypatch.setattr(serve, "refuse_unless_servable", lambda settings, process: None)
    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-serve-logging-pw")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "5")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "5")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with restored():
        yield calls


def test_adr0005_serve_passes_the_line_form_and_no_access_log(
    started: list[dict[str, Any]],
) -> None:
    serve.main()
    [call] = started
    assert call["app"] == "app.main:create_app"
    assert call["access_log"] is False
    assert call["log_config"] == log_config("backend")


def test_adr0005_serve_factory_is_only_a_parameter(started: list[dict[str, Any]]) -> None:
    serve.main("eko113_fixture_app:create")
    assert started[0]["app"] == "eko113_fixture_app:create"


@pytest.fixture
def output(capfd: pytest.CaptureFixture[str]) -> Iterator[Callable[[], str]]:
    with restored():
        install_for_test("backend")
        capfd.readouterr()
        yield lambda: capfd.readouterr().err


def test_adr0005_third_party_line_is_its_format_string(output: Callable[[], str]) -> None:
    logging.getLogger("uvicorn.error").info(
        '%s - "WebSocket %s" %d', "172.18.0.4:51000", f"/api/x?q={MARKER}", 403
    )
    logging.getLogger("uvicorn.access").warning('%s - "%s %s"', "c", "GET", f"/?q={MARKER}")
    text = output()
    lines, others = ll.json_lines(text)
    assert others == []
    assert [line["msg"] for line in lines] == ['%s - "WebSocket %s" %d', '%s - "%s %s"']
    assert ll.leaks(text, MARKER) == []
