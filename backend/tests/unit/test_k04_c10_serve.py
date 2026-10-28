"""K-04 / ADR-0004-C10: the web entry point stops before uvicorn spawns any worker process.

With several workers, uvicorn's supervisor restarts a worker that dies on a missing secret, so
the process would never exit; the settings are therefore read once, before uvicorn starts.
"""

from typing import Any

import pytest
import uvicorn

from app import serve


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append({"app": app, **kw}))
    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-serve-pw")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "5")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "5")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    return calls


def test_k04_c10_serve_starts_uvicorn_with_the_configured_workers(
    started: list[dict[str, Any]],
) -> None:
    serve.main()
    assert len(started) == 1
    assert started[0]["app"] == "app.main:create_app"
    assert started[0]["factory"] is True
    assert started[0]["workers"] == 2


@pytest.mark.parametrize("name", ["APP_DB_PASSWORD", "WEB_CONCURRENCY"])
@pytest.mark.parametrize("value", [None, ""])
def test_k04_c10_serve_stops_before_spawning_workers(
    started: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch, name: str, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as stopped:
        serve.main()
    assert name in str(stopped.value.code)
    assert started == []
