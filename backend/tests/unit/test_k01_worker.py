"""K-01: the worker entry module starts, does no work, and stops on request."""

import threading

import pytest

from app.worker import run


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_PASSWORD", "synthetic-worker-pw")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "2")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "0")


def test_k01_worker_returns_zero_when_asked_to_stop(env: None) -> None:
    stop = threading.Event()
    stop.set()
    assert run(stop) == 0


def test_k01_worker_waits_until_asked_to_stop(env: None) -> None:
    stop = threading.Event()
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(run(stop)))
    thread.start()
    thread.join(timeout=0.5)
    assert thread.is_alive()
    stop.set()
    thread.join(timeout=5)
    assert result == [0]


def test_k04_c10_worker_stops_on_missing_secret_naming_it(
    env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_DB_PASSWORD")
    with pytest.raises(SystemExit) as stopped:
        run(threading.Event())
    assert "APP_DB_PASSWORD" in str(stopped.value.code)
