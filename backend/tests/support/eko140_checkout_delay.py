"""The observed blocker factory whose session-store checkouts keep their connection busy for a
controlled delay on one process (EKO-1-40); none of this ships.

`create_delayed_on_holder` and `create_delayed_on_non_holder` serve what
`tests.support.eko138_observed_app:create_with_blockers` serves. Every checkout of the shipped
`SessionStore` (`find`, `refresh_holder`, every waiter's probe) is delayed once it has its
connection, so the connection stays checked out for `DELAY_SECONDS` more, standing in for a host
on which each checkout takes that much longer:

- on the holder's process: from the moment a request of this process took the session's refresh
  lock until the process stops;
- on the non-holder process: from the moment a request of this process found the lock taken,
  while no request of this process holds it.

Neither process knows beforehand which one wins the lock, so the delay starts at that instant and
no checkout before it is delayed. `/__eko201/state` reports the delay under `delay`, and each
delayed checkout of a tagged request carries `delayed` (the seconds it was held for the delay).
`EKO140_DELAY_SECONDS`, if set in the process's environment, replaces `DELAY_SECONDS`; it exists
to record other magnitudes as evidence, and no test sets it.
"""

import dataclasses
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from fastapi import FastAPI
from sqlalchemy import Connection

from app.data.database import Database
from app.data.sessions import RefreshHolder
from tests.support import eko138_observed_app, eko201_fixture_app
from tests.support.eko138_observed_app import ObservedAuthenticator, ObservedStore, Observer, Phases

DELAY_SECONDS = 0.2
DELAY_ENV = "EKO140_DELAY_SECONDS"

On = Literal["holder", "non-holder"]


class Delay:
    """When this process delays its checkouts and how often it did; changed under one lock."""

    def __init__(self, seconds: float, on: On) -> None:
        self.seconds = seconds
        self.on = on
        self.lock = threading.Lock()
        self.holder_here = False
        self.lock_seen_taken = False
        self.active_since: float | None = None
        self.applied = 0

    def saw(self, holder: bool) -> None:
        with self.lock:
            if holder:
                self.holder_here = True
            else:
                self.lock_seen_taken = True
            if self._active() and self.active_since is None:
                self.active_since = time.monotonic()

    def _active(self) -> bool:
        if self.on == "holder":
            return self.holder_here
        return self.lock_seen_taken and not self.holder_here

    def take(self) -> float:
        """The seconds the checkout just made must keep its connection; 0 when inactive."""
        with self.lock:
            if not self._active() or self.seconds <= 0:
                return 0.0
            self.applied += 1
            return self.seconds

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "seconds": self.seconds,
                "on": self.on,
                "holder_here": self.holder_here,
                "lock_seen_taken": self.lock_seen_taken,
                "active_since": self.active_since,
                "applied": self.applied,
            }


class DelayedPhases(Phases):
    def __init__(self, delay: Delay) -> None:
        super().__init__()
        self.delay = delay

    def mark_delayed(self, seconds: float) -> None:
        """The current tagged request's open checkout was held `seconds` for the delay."""
        tag = eko138_observed_app._tag.get()
        if tag is None:
            return
        with self.lock:
            checkouts = self.requests.get(tag, {}).get("checkouts", [])
            if checkouts and "ended" not in checkouts[-1]:
                checkouts[-1]["delayed"] = seconds

    def snapshot(self, database: Database) -> dict[str, Any]:
        found = super().snapshot(database)
        found["delay"] = self.delay.snapshot()
        return found


class DelayedStore(ObservedStore):
    phases: DelayedPhases

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        with super()._connection() as connection:
            seconds = self.phases.delay.take()
            if seconds:
                self.phases.mark_delayed(seconds)
                # Held, not idle: the connection stays checked out while the request sleeps.
                time.sleep(seconds)
            yield connection

    @contextmanager
    def refresh_holder(self, session_id: int) -> Iterator[RefreshHolder | None]:
        with super().refresh_holder(session_id) as holder:
            self.phases.delay.saw(holder is not None)
            yield holder


def _delayed(app: FastAPI, on: On) -> FastAPI:
    seconds = float(os.environ.get(DELAY_ENV, DELAY_SECONDS))
    phases = DelayedPhases(Delay(seconds, on))
    database: Database = app.state.database
    shipped = app.state.auth
    fields = {f.name: getattr(shipped, f.name) for f in dataclasses.fields(shipped)}
    fields["store"] = DelayedStore(database, phases)
    observed = ObservedAuthenticator(**fields)
    observed.phases = phases
    app.state.auth = observed
    # Added last, so it is outermost, as in `eko138_observed_app._observed`.
    app.add_middleware(Observer, phases=phases, database=database)
    return app


def create_delayed_on_holder() -> FastAPI:
    return _delayed(eko201_fixture_app.create_with_blockers(), "holder")


def create_delayed_on_non_holder() -> FastAPI:
    return _delayed(eko201_fixture_app.create_with_blockers(), "non-holder")
