"""Retention of sessions, login transactions and staff display-name copies (ADR-0005 *Retention*,
ADR-0005-C8, C9 in part; ADR-0003 addendum of 2026-11-02, G-1 A; ADR-0005 addendum of EKO-3-08),
run by the worker.

A session is deleted, with its encrypted tokens, once 10 hours have passed since its creation; a
login transaction once 1 hour has; a display-name copy that no record of the reference set refers
to once 180 x 24 hours have passed since the subject's last login. "No later than" includes the
bound, and the interval between runs counts within it, so the worker sleeps until the earliest
bound still ahead, never longer than `MAX_WAIT_SECONDS`. The run writes counts only, never a
subject or a name.
"""

import logging
from datetime import datetime

from app.core.clock import Clock
from app.data.database import Database
from app.data.sessions import SessionStore, StorageUnavailable
from app.data.staff import StaffStore, delete_unreferenced_copies
from app.domain.session_policy import LOGIN_TRANSACTION_RETENTION, SESSION_RETENTION
from app.domain.staff import COPY_RETENTION

logger = logging.getLogger(__name__)

MAX_WAIT_SECONDS = 60.0
RETRY_SECONDS = 10.0


def sweep(database: Database, now: datetime) -> tuple[int, int, int]:
    """Deletes what has reached its bound at `now`; the counts of sessions, transactions and
    display-name copies."""
    sessions, transactions = SessionStore(database).delete_created_before(
        now - SESSION_RETENTION, now - LOGIN_TRANSACTION_RETENTION
    )
    return sessions, transactions, delete_unreferenced_copies(database, now - COPY_RETENTION)


def seconds_until_next(database: Database, now: datetime) -> float:
    session, transaction = SessionStore(database).earliest_created()
    login = StaffStore(database).earliest_login_after(now - COPY_RETENTION)
    bounds = [
        start + retention
        for start, retention in (
            (session, SESSION_RETENTION),
            (transaction, LOGIN_TRANSACTION_RETENTION),
            (login, COPY_RETENTION),
        )
        if start is not None
    ]
    if not bounds:
        return MAX_WAIT_SECONDS
    return max(0.0, min(MAX_WAIT_SECONDS, (min(bounds) - now).total_seconds()))


def run_once(database: Database, clock: Clock) -> float:
    """One sweep; the seconds to wait before the next."""
    try:
        sessions, transactions, copies = sweep(database, clock.now())
        if sessions or transactions or copies:
            logger.info("retention deleted %d sessions, %d login transactions and %d "
                        "display-name copies", sessions, transactions, copies)  # fmt: skip
        return seconds_until_next(database, clock.now())
    except StorageUnavailable:
        return RETRY_SECONDS
