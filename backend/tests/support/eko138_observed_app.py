"""The EKO-2-01 blocker factories with an observation layer (EKO-1-38); none of this ships.

`create_with_blockers` and `create_unbounded_with_blockers` serve what the factories of the same
name in `tests/support/eko201_fixture_app.py` serve, plus one test path answered before them:
`/__eko201/state` returns, as JSON, what the running process records on its own monotonic clock:

- `pool_size`, `checked_out`: the process's pool, as SQLAlchemy counts it;
- `held`, `held_at`, `released_at`: the connection blockers' count, the instant `block` answered
  and the instant `release` arrived;
- `requests`: per request tagged by the `x-eko201-tag` header, its phase (`holding` while it
  refreshes the session in `Authenticator._hold`, `waiting` while it is in `Authenticator._wait`,
  `held` / `waited` after), its non-retried checkouts (`SessionStore.find`,
  `SessionStore.refresh_holder`) with start, end and outcome, its status and when it answered.

The shipped `Authenticator` and `SessionStore` do the work; the subclasses only record around it.
"""

import copy
import dataclasses
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI
from sqlalchemy.pool import QueuePool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.sessions import Authenticator
from app.data.database import Database
from app.data.sessions import RefreshHolder, SessionStore, StorageUnavailable, StoredSession
from app.domain.caller import Caller
from tests.support import eko201_fixture_app

STATE_PATH = "/__eko201/state"
TAG_HEADER = "x-eko201-tag"

_tag: ContextVar[str | None] = ContextVar("eko201_tag", default=None)


class Phases:
    """The process's record; every change is under one lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: dict[str, dict[str, Any]] = {}
        self.held = 0
        self.held_at: float | None = None
        self.released_at: float | None = None

    def _entry(self, tag: str) -> dict[str, Any]:
        return self.requests.setdefault(tag, {"phase": "arrived", "checkouts": []})

    def set_phase(self, phase: str) -> None:
        tag = _tag.get()
        if tag is not None:
            with self.lock:
                self._entry(tag)["phase"] = phase

    def answered(self, tag: str, status: int | None) -> None:
        with self.lock:
            entry = self._entry(tag)
            entry["status"] = status
            entry["answered"] = time.monotonic()

    def blocked(self, held: int) -> None:
        with self.lock:
            self.held = held
            self.held_at = time.monotonic()

    def released(self) -> None:
        with self.lock:
            self.held = 0
            self.released_at = time.monotonic()

    @contextmanager
    def checkout(self, step: str) -> Iterator[dict[str, Any]]:
        record: dict[str, Any] = {"step": step, "started": time.monotonic()}
        tag = _tag.get()
        if tag is not None:
            with self.lock:
                self._entry(tag)["checkouts"].append(record)
        try:
            yield record
        except StorageUnavailable:
            record.setdefault("ended", time.monotonic())
            record.setdefault("outcome", "unavailable")
            raise
        record.setdefault("ended", time.monotonic())
        record.setdefault("outcome", "ok")

    def snapshot(self, database: Database) -> dict[str, Any]:
        pool = database.engine.pool
        if not isinstance(pool, QueuePool):
            raise TypeError(f"the application engine's pool is a {type(pool).__name__}")
        with self.lock:
            return {
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "held": self.held,
                "held_at": self.held_at,
                "released_at": self.released_at,
                "requests": copy.deepcopy(self.requests),
            }


class ObservedStore(SessionStore):
    def __init__(self, database: Database, phases: Phases) -> None:
        super().__init__(database)
        self.phases = phases

    def find(self, session_hash: str) -> StoredSession | None:
        with self.phases.checkout("find"):
            return super().find(session_hash)

    @contextmanager
    def refresh_holder(self, session_id: int) -> Iterator[RefreshHolder | None]:
        with self.phases.checkout("refresh_holder") as record:
            with super().refresh_holder(session_id) as holder:
                record["ended"] = time.monotonic()
                record["outcome"] = "lock taken" if holder is None else "holder"
                yield holder


class ObservedAuthenticator(Authenticator):
    phases: Phases

    def _hold(self, holder: RefreshHolder, seen: StoredSession) -> Caller:
        self.phases.set_phase("holding")
        try:
            return super()._hold(holder, seen)
        finally:
            self.phases.set_phase("held")

    def _wait(self, seen: StoredSession, deadline: float) -> Caller:
        self.phases.set_phase("waiting")
        try:
            return super()._wait(seen, deadline)
        finally:
            self.phases.set_phase("waited")


class Observer:
    def __init__(self, app: ASGIApp, phases: Phases, database: Database) -> None:
        self.app = app
        self.phases = phases
        self.database = database

    async def _state(self, send: Send) -> None:
        body = json.dumps(self.phases.snapshot(self.database)).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})  # fmt: skip
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == STATE_PATH:
            await self._state(send)
            return
        if path == "/__eko201/release":
            self.phases.released()
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        tag = headers.get(TAG_HEADER.encode())
        status: list[int] = []
        body: list[bytes] = []

        async def recorded(message: Message) -> None:
            if message["type"] == "http.response.start":
                status.append(int(message["status"]))
            elif message["type"] == "http.response.body":
                body.append(bytes(message.get("body", b"")))
            await send(message)

        token = _tag.set(None if tag is None else tag.decode("ascii"))
        try:
            await self.app(scope, receive, recorded)
        finally:
            _tag.reset(token)
        if path == "/__eko201/block":
            self.phases.blocked(int(b"".join(body)))
        elif tag is not None:
            self.phases.answered(tag.decode("ascii"), status[0] if status else None)


def _observed(app: FastAPI) -> FastAPI:
    phases = Phases()
    database: Database = app.state.database
    shipped: Authenticator = app.state.auth
    fields = {f.name: getattr(shipped, f.name) for f in dataclasses.fields(shipped)}
    fields["store"] = ObservedStore(database, phases)
    observed = ObservedAuthenticator(**fields)
    observed.phases = phases
    app.state.auth = observed
    # Added last, so it is outermost: it sees `block` answer and `release` arrive.
    app.add_middleware(Observer, phases=phases, database=database)
    return app


def create_with_blockers() -> FastAPI:
    return _observed(eko201_fixture_app.create_with_blockers())


def create_unbounded_with_blockers() -> FastAPI:
    return _observed(eko201_fixture_app.create_unbounded_with_blockers())
