"""Server-side sessions, login transactions and the per-session refresh lock (ADR-0003 *Browser
flow*, *How a request is verified*; addendum of 2026-11-02, G-5 A).

Only hashes of the browser's identifiers are stored, and tokens only as the ciphertext `auth`
seals; this module never sees a token or an identifier in clear. Every read and write is its own
short transaction. The refresh lock is a session-level advisory lock in the two-key form, so it
never shares a key with the single-key migration lock (ADR-0004): it is taken only after the
transaction that read the session has committed, no transaction stays open while it is held,
and ending the holder's database session releases it.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, delete, func, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.data.database import Database
from app.data.models import AppSession, LoginTransaction

logger = logging.getLogger(__name__)

# First key of every refresh lock: "EK2" and 0x01, as a positive int4.
REFRESH_LOCK_CLASS = 0x454B3201


class StorageUnavailable(Exception):
    """The application database could not be reached, or no pooled connection was free in time."""


@dataclass(frozen=True)
class StoredSession:
    id: int
    session_hash: str
    subject: str
    tokens: bytes
    access_expires_at: datetime
    created_at: datetime
    last_used_at: datetime


@dataclass(frozen=True)
class StoredTransaction:
    state_hash: str
    nonce_hash: str
    verifier: bytes
    return_to: str
    created_at: datetime


@dataclass(frozen=True)
class Probe:
    """A waiter's look at a session: the row as committed, and whether no holder had the lock."""

    session: StoredSession | None
    lock_free: bool


def lock_key(session_id: int) -> int:
    """The session's identity as the lock's signed int4 second key."""
    return ((session_id + 2**31) % 2**32) - 2**31


_SESSION_COLUMNS = (
    AppSession.id,
    AppSession.session_hash,
    AppSession.subject,
    AppSession.tokens,
    AppSession.access_expires_at,
    AppSession.created_at,
    AppSession.last_used_at,
)
_TRY_LOCK = text("SELECT pg_try_advisory_lock(CAST(:cls AS integer), CAST(:key AS integer))")
_UNLOCK = text("SELECT pg_advisory_unlock(CAST(:cls AS integer), CAST(:key AS integer))")


def _session(connection: Connection, where: object) -> StoredSession | None:
    row = connection.execute(select(*_SESSION_COLUMNS).where(where)).one_or_none()  # type: ignore[arg-type]  # a column expression
    return None if row is None else StoredSession(*row)


def _try_lock(connection: Connection, session_id: int) -> bool:
    acquired = connection.execute(
        _TRY_LOCK, {"cls": REFRESH_LOCK_CLASS, "key": lock_key(session_id)}
    ).scalar_one()
    connection.commit()
    return bool(acquired)


def _unlock(connection: Connection, session_id: int) -> None:
    released = connection.execute(
        _UNLOCK, {"cls": REFRESH_LOCK_CLASS, "key": lock_key(session_id)}
    ).scalar_one()
    connection.commit()
    if not released:
        logger.warning("refresh lock was not held at release")


class RefreshHolder:
    """The one request refreshing a session: holds the lock on its own checked-out connection."""

    def __init__(self, connection: Connection, session_id: int) -> None:
        self._connection = connection
        self.session_id = session_id

    def read(self) -> StoredSession | None:
        found = _session(self._connection, AppSession.id == self.session_id)
        self._connection.commit()
        return found

    def store_tokens(self, tokens: bytes, access_expires_at: datetime, now: datetime) -> None:
        self._connection.execute(
            update(AppSession)
            .where(AppSession.id == self.session_id)
            .values(
                tokens=tokens,
                access_expires_at=access_expires_at,
                last_used_at=func.greatest(AppSession.last_used_at, now),
            )
        )
        self._connection.commit()

    def delete(self) -> None:
        self._connection.execute(delete(AppSession).where(AppSession.id == self.session_id))
        self._connection.commit()


class SessionStore:
    def __init__(self, database: Database) -> None:
        self._engine = database.engine

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        try:
            with self._engine.connect() as connection:
                yield connection
        except SQLAlchemyError as exc:
            # The type only: driver messages name hosts, roles and statement parameters.
            logger.warning("session storage unavailable: %s", type(exc).__name__)
            raise StorageUnavailable from None

    # Login transactions ------------------------------------------------------------------------

    def add_transaction(
        self,
        transaction_hash: str,
        state_hash: str,
        nonce_hash: str,
        verifier: bytes,
        return_to: str,
        now: datetime,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                insert(LoginTransaction).values(
                    transaction_hash=transaction_hash,
                    state_hash=state_hash,
                    nonce_hash=nonce_hash,
                    verifier=verifier,
                    return_to=return_to,
                    created_at=now,
                )
            )
            connection.commit()

    def take_transaction(self, transaction_hash: str) -> StoredTransaction | None:
        """Deletes the transaction and returns it: a callback consumes it whatever its outcome."""
        with self._connection() as connection:
            row = connection.execute(
                delete(LoginTransaction)
                .where(LoginTransaction.transaction_hash == transaction_hash)
                .returning(
                    LoginTransaction.state_hash,
                    LoginTransaction.nonce_hash,
                    LoginTransaction.verifier,
                    LoginTransaction.return_to,
                    LoginTransaction.created_at,
                )
            ).one_or_none()
            connection.commit()
        return None if row is None else StoredTransaction(*row)

    # Sessions ----------------------------------------------------------------------------------

    def create_session(
        self,
        session_hash: str,
        subject: str,
        tokens: bytes,
        access_expires_at: datetime,
        now: datetime,
        replaced_hash: str | None,
    ) -> None:
        """A new session; the one the browser presented before the login, if any, is deleted."""
        with self._connection() as connection:
            if replaced_hash is not None:
                connection.execute(
                    delete(AppSession).where(AppSession.session_hash == replaced_hash)
                )
            connection.execute(
                insert(AppSession).values(
                    session_hash=session_hash,
                    subject=subject,
                    tokens=tokens,
                    access_expires_at=access_expires_at,
                    created_at=now,
                    last_used_at=now,
                )
            )
            connection.commit()

    def find(self, session_hash: str) -> StoredSession | None:
        with self._connection() as connection:
            found = _session(connection, AppSession.session_hash == session_hash)
            connection.commit()
        return found

    def touch(self, session_id: int, now: datetime) -> None:
        with self._connection() as connection:
            connection.execute(
                update(AppSession)
                .where(AppSession.id == session_id)
                .values(last_used_at=func.greatest(AppSession.last_used_at, now))
            )
            connection.commit()

    def delete(self, session_id: int) -> None:
        with self._connection() as connection:
            connection.execute(delete(AppSession).where(AppSession.id == session_id))
            connection.commit()

    # Refresh lock ------------------------------------------------------------------------------

    @contextmanager
    def refresh_holder(self, session_id: int) -> Iterator[RefreshHolder | None]:
        """One checkout: the lock is tried and, when taken, held on that connection until exit.

        Yields None, with the connection already returned, when another holder has the lock.
        """
        with self._connection() as connection:
            if not _try_lock(connection, session_id):
                connection.close()
                yield None
                return
            try:
                yield RefreshHolder(connection, session_id)
            finally:
                try:
                    connection.rollback()
                    _unlock(connection, session_id)
                except SQLAlchemyError:
                    # Closing the server session is the release that cannot be skipped.
                    connection.invalidate()
                    raise

    def probe(self, session_id: int) -> Probe:
        """A waiter's short look, on a connection returned before this returns.

        The lock is tried first: taken means the holder has finished, so the row read after it is
        what that holder committed; the lock is given back at once and never held by a waiter.
        """
        with self._connection() as connection:
            free = _try_lock(connection, session_id)
            try:
                found = _session(connection, AppSession.id == session_id)
                connection.commit()
            finally:
                if free:
                    _unlock(connection, session_id)
        return Probe(found, free)

    # Retention ---------------------------------------------------------------------------------

    def delete_created_before(
        self, session_cutoff: datetime, transaction_cutoff: datetime
    ) -> tuple[int, int]:
        """Sessions and transactions created at or before their cutoff; their counts."""
        with self._connection() as connection:
            sessions = connection.execute(
                delete(AppSession).where(AppSession.created_at <= session_cutoff)
            ).rowcount
            transactions = connection.execute(
                delete(LoginTransaction).where(LoginTransaction.created_at <= transaction_cutoff)
            ).rowcount
            connection.commit()
        return int(sessions or 0), int(transactions or 0)

    def earliest_created(self) -> tuple[datetime | None, datetime | None]:
        with self._connection() as connection:
            session = connection.execute(select(func.min(AppSession.created_at))).scalar_one()
            transaction = connection.execute(
                select(func.min(LoginTransaction.created_at))
            ).scalar_one()
            connection.commit()
        return session, transaction
