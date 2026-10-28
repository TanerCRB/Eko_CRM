import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# A marker value: it must never appear in a response body or an error message.
SYNTHETIC_PASSWORD = "synthetic-marker-pw-7f3a"


def closed_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


@pytest.fixture
def backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_DB_PORT", str(closed_local_port()))
    monkeypatch.setenv("APP_DB_PASSWORD", SYNTHETIC_PASSWORD)
    monkeypatch.setenv("APP_DB_POOL_SIZE", "2")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "0")


@pytest.fixture
def client(backend_env: None) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c
