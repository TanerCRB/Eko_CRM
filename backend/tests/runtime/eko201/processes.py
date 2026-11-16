"""Backend processes for the cross-process carriers (K-04, K-05): each is its own uvicorn process
with its own connection pool, serving the shipped factory or a fixture factory of
`tests/support/eko201_fixture_app.py`, against the throwaway PostgreSQL and the OIDC stub."""

import os
import socket
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

import httpx
import jwt

from tests.runtime.eko201.conftest import ORIGIN, SESSION_COOKIE, SESSION_KEY
from tests.support import oidc_stub
from tests.support.pg_instance import BACKEND, Postgres

SHIPPED = "app.main:create_app"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


@dataclass
class Backend:
    process: subprocess.Popen[bytes]
    url: str

    def get(self, path: str, session: str | None = None, timeout: float = 30) -> httpx.Response:
        cookies = {} if session is None else {"cookie": f"{SESSION_COOKIE}={session}"}
        return httpx.get(self.url + path, headers=cookies, timeout=timeout)

    def kill(self) -> None:
        self.process.kill()
        self.process.wait(timeout=30)


def backend_env(
    pg: Postgres, stub: oidc_stub.Stub, pool_size: int = 2, extra: dict[str, str] | None = None
) -> dict[str, str]:
    return {
        **os.environ,
        **pg.app_env(pool_size, 0),
        "APP_ORIGIN": ORIGIN,
        "APP_OIDC_ISSUER": stub.issuer,
        "APP_OIDC_CLIENT_SECRET": oidc_stub.CLIENT_SECRET,
        "APP_SESSION_ENCRYPTION_KEY": SESSION_KEY,
        **(extra or {}),
    }


@contextmanager
def backend(
    pg: Postgres,
    stub: oidc_stub.Stub,
    factory: str = SHIPPED,
    pool_size: int = 2,
    extra: dict[str, str] | None = None,
) -> Iterator[Backend]:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", factory, "--factory", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning", "--no-access-log"],
        cwd=BACKEND,
        env=backend_env(pg, stub, pool_size, extra),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # fmt: skip
    running = Backend(process, f"http://127.0.0.1:{port}")
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(running.url + "/api/health", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("backend process did not start")
            time.sleep(0.2)
        yield running
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=30)


@contextmanager
def backends(
    pg: Postgres, stub: oidc_stub.Stub, count: int = 2, **kwargs: object
) -> Iterator[list[Backend]]:
    with ExitStack() as stack:
        yield [stack.enter_context(backend(pg, stub, **kwargs)) for _ in range(count)]  # type: ignore[arg-type]


def login(target: Backend) -> str:
    """The real login flow through one backend process; returns the session cookie's value."""
    start = httpx.get(target.url + "/api/auth/login", follow_redirects=False)
    assert start.status_code == 303, start.text
    login_cookie = start.cookies.get("__Host-eko_login") or _cookie(start, "__Host-eko_login")
    at_idp = httpx.get(start.headers["location"], follow_redirects=False)
    callback = urllib.parse.urlsplit(at_idp.headers["location"])
    done = httpx.get(
        f"{target.url}{callback.path}?{callback.query}",
        headers={"cookie": f"__Host-eko_login={login_cookie}"},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text
    return _cookie(done, SESSION_COOKIE)


def _cookie(response: httpx.Response, name: str) -> str:
    for header in response.headers.get_list("set-cookie"):
        first = header.split(";", 1)[0]
        key, _, value = first.partition("=")
        if key.strip() == name:
            return value.strip()
    raise AssertionError(f"{name} not set")


# Short enough that the first request on the session finds the access token expired (the EKO-2-01
# K-04/K-05 premise), long enough to outlast the callback's verification (EKO-1-33): with the issue
# time truncated to a whole second, more than 5 s are left at minting, and a callback that takes 5 s
# ends on the read timeouts a login meets (`test_eko133_slow_callback.py`) before it verifies.
SHORT_LIFESPAN_SECONDS = 6
LONG_LIFESPAN_SECONDS = 240


def access_expiry(token: str) -> float | None:
    """The `exp` of an access token the stub issued; None for any other token."""
    if token.count(".") != 2:
        return None
    claims = jwt.decode(token, options={"verify_signature": False})
    return float(claims["exp"]) if claims.get("typ") == "Bearer" else None


def expired_logins(stub: oidc_stub.Stub, targets: Sequence[Backend]) -> list[str]:
    """One login per target with a short-lived access token, then a wait on the real clock the
    backend processes share with this one until every such token has expired. Tokens issued later
    (refreshes) are long-lived. Returns the session cookies' values."""
    first = len(stub.issued)
    stub.access_lifespan_seconds = SHORT_LIFESPAN_SECONDS
    try:
        sessions = [login(target) for target in targets]
    finally:
        stub.access_lifespan_seconds = LONG_LIFESPAN_SECONDS
    expiries = [e for e in map(access_expiry, stub.issued[first:]) if e is not None]
    assert len(expiries) == len(targets), expiries
    expiry = max(expiries)
    while time.time() <= expiry:
        time.sleep(max(0.01, min(0.1, expiry - time.time())))
    assert time.time() > expiry, "the access token has not expired before the first request"
    return sessions


def expired_login(stub: oidc_stub.Stub, target: Backend) -> str:
    [session] = expired_logins(stub, [target])
    return session
