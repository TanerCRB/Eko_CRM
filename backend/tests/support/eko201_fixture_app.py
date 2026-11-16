"""Fixture factories for the EKO-2-01 cross-process carriers; none of this ships.

- `create_with_blockers`: the shipped `create_app()` plus an ASGI layer answering two test paths
  before routing: `/__eko201/block?count=N` checks out N connections of the process's own pool and
  holds them, `/__eko201/release` returns them (ADR-0002-C16's "connection blockers").
- `create_unbounded_with_blockers`: the same, with the engine built without `pool_timeout`, so
  SQLAlchemy's default 30-second checkout wait applies (ADR-0002-C16's opposite case).
- `create_with_pause`: the shipped application whose refresh call pauses at the point named by
  `EKO201_PAUSE` (`before_send` or `after_answer`) after writing the file `EKO201_MARKER`, so a
  test can kill the holder there (ADR-0003-C28).
"""

import os
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send


class Blockers:
    def __init__(self, app: ASGIApp, served: FastAPI) -> None:
        self.app = app
        self.served = served
        self.held: list[Any] = []
        self.release = threading.Event()
        self.thread: threading.Thread | None = None

    def _hold(self, count: int, acquired: threading.Event) -> None:
        engine = self.served.state.database._engine
        deadline = time.monotonic() + 10
        while len(self.held) < count and time.monotonic() < deadline:
            try:
                self.held.append(engine.connect())
            except Exception:  # noqa: BLE001 - a checkout timeout here only means "retry"
                time.sleep(0.05)
        acquired.set()
        self.release.wait(timeout=120)
        for connection in self.held:
            connection.close()
        self.held.clear()

    async def _answer(self, send: Send, body: bytes) -> None:
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})  # fmt: skip
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path == "/__eko201/block":
            query = dict(urllib.parse.parse_qsl(scope.get("query_string", b"").decode()))
            acquired = threading.Event()
            self.release.clear()
            self.thread = threading.Thread(
                target=self._hold, args=(int(query["count"]), acquired), daemon=True
            )
            self.thread.start()
            while not acquired.is_set():
                time.sleep(0.01)
            await self._answer(send, str(len(self.held)).encode())
            return
        if path == "/__eko201/release":
            self.release.set()
            if self.thread is not None:
                self.thread.join(timeout=10)
            await self._answer(send, b"released")
            return
        await self.app(scope, receive, send)


def _with_blockers(app: FastAPI) -> FastAPI:
    app.add_middleware(Blockers, served=app)
    return app


def create_with_blockers() -> FastAPI:
    from app.main import create_app

    return _with_blockers(create_app())


def create_unbounded_with_blockers() -> FastAPI:
    from sqlalchemy import create_engine

    from app.data import database
    from app.main import create_app

    def unbounded(settings: Any) -> Any:
        return create_engine(
            database.database_url(settings),
            pool_size=settings.app_db_pool_size,
            max_overflow=settings.app_db_max_overflow,
            pool_pre_ping=True,
            connect_args=database.connect_args(settings),
        )

    # The opposite case: SQLAlchemy's default checkout wait.
    database.create_app_engine = unbounded
    return _with_blockers(create_app())


def create_with_pause() -> FastAPI:
    from app.auth import oidc
    from app.main import create_app

    point = os.environ["EKO201_PAUSE"]
    marker = Path(os.environ["EKO201_MARKER"])
    original = oidc.OidcClient.refresh

    def paused(self: Any, refresh_token: str) -> Any:
        if point == "before_send":
            marker.write_text("before_send", encoding="utf-8")
            time.sleep(120)
        answer = original(self, refresh_token)
        if point == "after_answer":
            marker.write_text("after_answer", encoding="utf-8")
            time.sleep(120)
        return answer

    oidc.OidcClient.refresh = paused  # type: ignore[method-assign]  # the holder's pause point
    return create_app()
