"""EKO-2-01 backend carriers: real PostgreSQL, a local OIDC stub, the shipped `create_app()`.

The application is built in-process by its own factory with synthetic settings pointing at the
throwaway server and the stub (`tests/support/oidc_stub.py`); no running Keycloak is needed. The
browser is played by `Browser`: it keeps cookies itself, so every cookie the backend sets is read
from the response headers and none is kept unless the test keeps it.
"""

import base64
import time
import urllib.parse
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support import oidc_stub
from tests.support.pg_instance import Postgres, postgres

ORIGIN = "https://app.test"
SESSION_COOKIE = "__Host-eko_session"
LOGIN_COOKIE = "__Host-eko_login"
SAFE = {"GET", "HEAD", "OPTIONS"}
SESSION_KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


@pytest.fixture(scope="session")
def pg() -> Iterator[Postgres]:
    with postgres() as instance:
        yield instance


@pytest.fixture
def clean(pg: Postgres) -> None:
    with pg.connect() as connection:
        connection.execute("TRUNCATE app_session, login_transaction")


@pytest.fixture
def stub(clean: None) -> Iterator[oidc_stub.Stub]:
    with oidc_stub.StubServer() as running:
        yield running


class FakeClock:
    """The application's clock under test: the instant is set, waiting is real."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def advance(self, **delta: float) -> None:
        self.at += timedelta(**delta)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@pytest.fixture
def clock(stub: oidc_stub.Stub) -> FakeClock:
    fake = FakeClock(datetime(2026, 11, 12, 8, 0, tzinfo=UTC))
    stub.now = fake.now
    return fake


def auth_env(pg: Postgres, stub: oidc_stub.Stub, **overrides: str) -> dict[str, str]:
    return {
        **pg.app_env(),
        "APP_ORIGIN": ORIGIN,
        "APP_OIDC_ISSUER": stub.issuer,
        "APP_OIDC_CLIENT_SECRET": oidc_stub.CLIENT_SECRET,
        "APP_SESSION_ENCRYPTION_KEY": SESSION_KEY,
        **overrides,
    }


AppFactory = Callable[..., FastAPI]


@pytest.fixture
def make_app(
    pg: Postgres, stub: oidc_stub.Stub, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> AppFactory:
    """`create_app()` under the given settings, on the test's clock."""
    from app.main import create_app

    def build(**overrides: str) -> FastAPI:
        with monkeypatch.context() as scoped:
            for name, value in auth_env(pg, stub, **overrides).items():
                scoped.setenv(name, value)
            app = create_app()
        # The application's clock is the test's; absent before the feature exists.
        auth = getattr(app.state, "auth", None)
        if auth is not None:
            auth.clock = clock
        return app

    return build


@dataclass
class SetCookie:
    name: str
    value: str
    attributes: dict[str, str]

    @property
    def cleared(self) -> bool:
        return self.attributes.get("max-age") == "0" or not self.value


def set_cookies(response: httpx.Response) -> list[SetCookie]:
    found = []
    for header in response.headers.get_list("set-cookie"):
        first, *rest = [part.strip() for part in header.split(";")]
        name, _, value = first.partition("=")
        attributes = {}
        for part in rest:
            key, _, val = part.partition("=")
            attributes[key.lower()] = val
        found.append(SetCookie(name, value.strip('"'), attributes))
    return found


@dataclass
class Browser:
    client: TestClient
    jar: dict[str, str] = field(default_factory=dict)
    responses: list[httpx.Response] = field(default_factory=list)

    def send(
        self, method: str, path: str, origin: str | None = ORIGIN, **kwargs: Any
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self.jar:
            headers["cookie"] = "; ".join(f"{k}={v}" for k, v in self.jar.items())
        if origin is not None and method not in SAFE:
            headers["origin"] = origin
        response: httpx.Response = self.client.request(
            method, path, headers=headers, follow_redirects=False, **kwargs
        )
        self.client.cookies.clear()
        self.responses.append(response)
        for cookie in set_cookies(response):
            if cookie.cleared:
                self.jar.pop(cookie.name, None)
            else:
                self.jar[cookie.name] = cookie.value
        return response

    def start_login(self, return_to: str = "/") -> httpx.Response:
        return self.send("GET", "/api/auth/login", params={"return_to": return_to})

    def at_identity_server(self, start: httpx.Response) -> str:
        """The callback path and query the stub redirects the browser to."""
        assert start.status_code == 303, start.text
        answer = httpx.get(start.headers["location"], follow_redirects=False)
        assert answer.status_code == 302, answer.text
        target = urllib.parse.urlsplit(answer.headers["location"])
        assert f"{target.scheme}://{target.netloc}" == ORIGIN
        return f"{target.path}?{target.query}"

    def login(self, return_to: str = "/") -> httpx.Response:
        return self.send("GET", self.at_identity_server(self.start_login(return_to)))

    @property
    def session(self) -> str | None:
        return self.jar.get(SESSION_COOKIE)


@pytest.fixture
def browser_for() -> Iterator[Callable[[FastAPI], Browser]]:
    clients: list[TestClient] = []

    def open_browser(app: FastAPI) -> Browser:
        client = TestClient(app, base_url=ORIGIN)
        client.__enter__()
        clients.append(client)
        return Browser(client)

    yield open_browser
    for client in clients:
        client.__exit__(None, None, None)


def session_count(pg: Postgres) -> int:
    return int(pg.rows("SELECT count(*) FROM app_session")[0][0])


def transaction_count(pg: Postgres) -> int:
    return int(pg.rows("SELECT count(*) FROM login_transaction")[0][0])
