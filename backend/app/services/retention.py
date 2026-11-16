"""Retention of sessions and login transactions (ADR-0005 *Retention*, ADR-0005-C8; ADR-0003
addendum of 2026-11-02, G-1 A), run by the worker.

A session is deleted, with its encrypted tokens, once 10 hours have passed since its creation; a
login transaction once 1 hour has. "No later than" includes the bound, and the interval between
runs counts within it, so the worker sleeps until the earliest bound still ahead, never longer
than `MAX_WAIT_SECONDS`.
"""

import logging
from datetime import datetime

from app.core.clock import Clock
from app.data.database import Database
from app.data.sessions import SessionStore, StorageUnavailable
from app.domain.session_policy import LOGIN_TRANSACTION_RETENTION, SESSION_RETENTION

logger = logging.getLogger(__name__)

MAX_WAIT_SECONDS = 60.0
RETRY_SECONDS = 10.0


def sweep(database: Database, now: datetime) -> tuple[int, int]:
    """Deletes what has reached its bound at `now`; the counts of sessions and transactions."""
    return SessionStore(database).delete_created_before(
        now - SESSION_RETENTION, now - LOGIN_TRANSACTION_RETENTION
    )


def seconds_until_next(database: Database, now: datetime) -> float:
    session, transaction = SessionStore(database).earliest_created()
    bounds = [
        created + retention
        for created, retention in (
            (session, SESSION_RETENTION),
            (transaction, LOGIN_TRANSACTION_RETENTION),
        )
        if created is not None
    ]
    if not bounds:
        return MAX_WAIT_SECONDS
    return max(0.0, min(MAX_WAIT_SECONDS, (min(bounds) - now).total_seconds()))


def run_once(database: Database, clock: Clock) -> float:
    """One sweep; the seconds to wait before the next."""
    try:
        sessions, transactions = sweep(database, clock.now())
        if sessions or transactions:
            logger.info("retention deleted %d sessions and %d login transactions",
                        sessions, transactions)  # fmt: skip
        return seconds_until_next(database, clock.now())
    except StorageUnavailable:
        return RETRY_SECONDS
