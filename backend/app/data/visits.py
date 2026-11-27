"""Visits in PostgreSQL: the only module that reads or writes the visit table (ADR-0003-C35, the
EKO-4-01 addendum's ADR-0003-C42).

Every function here takes a scope as a required argument and applies it in the statement that
selects or writes the rows: a visit read or list compares the visit's own `owner_subject`, never
its customer's, and the customer a create names is selected under the caller's own-records scope
in the transaction that inserts the visit. A visit outside the scope is never loaded, so "not
visible" and "missing" are the same `None`. The customer values a visit is shown with are read in
the visit's statement, under the visit's scope (A-3 A).

A period arrives as two instants, already computed from Europe/Warsaw dates by
`app.domain.warsaw`; no time-zone arithmetic happens in SQL (ADR-0002-C8). Identifiers are UUIDv4
values generated here, never by the database (ADR-0006). Nothing here reads a clock: the state is
derived by the service from its injected one.
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, Connection, Row, Select, insert, select, true
from sqlalchemy.exc import SQLAlchemyError

from app.data.database import Database
from app.data.models import CustomerRow, VisitRow
from app.data.sessions import StorageUnavailable
from app.domain.customers import Address
from app.domain.ownership import AllRecords, OwnedBy, VisibilityScope
from app.domain.visits import NotPlanned, Visit, VisitCustomer, VisitDraft
from app.domain.warsaw import Period

logger = logging.getLogger(__name__)


def new_identifier() -> uuid.UUID:
    """A random (version 4) identifier: no state a restore could rewind."""
    return uuid.uuid4()


def _visible(scope: VisibilityScope) -> ColumnElement[bool]:
    """The visit scope, on the visit's own owner (ADR-0003-C42)."""
    if isinstance(scope, AllRecords):
        return true()
    return VisitRow.owner_subject == scope.subject


def _shown(scope: VisibilityScope) -> Select[Any]:
    """A visit with the customer values it is shown with, in one statement under the visit's
    scope; the customer's own owner is never compared."""
    return (
        select(
            VisitRow.id,
            VisitRow.starts_at,
            VisitRow.ends_at,
            VisitRow.own_address,
            CustomerRow.id,
            CustomerRow.name,
            CustomerRow.street,
            CustomerRow.postal_code,
            CustomerRow.town,
            CustomerRow.voivodeship,
            CustomerRow.county,
        )
        .join(CustomerRow, CustomerRow.id == VisitRow.customer_id)
        .where(_visible(scope))
    )


def _utc(instant: datetime) -> datetime:
    return instant.astimezone(UTC)


def _visit(row: Row[Any]) -> Visit:
    visit_id, starts_at, ends_at, own_address, customer_id, name, *place = row
    return Visit(
        id=visit_id,
        customer=VisitCustomer(customer_id, name, Address(*place)),
        starts_at=_utc(starts_at),
        ends_at=_utc(ends_at),
        own_address=own_address,
    )


def _find(connection: Connection, scope: VisibilityScope, visit_id: uuid.UUID) -> Visit | None:
    row = connection.execute(_shown(scope).where(VisitRow.id == visit_id)).first()
    return None if row is None else _visit(row)


class VisitStore:
    def __init__(self, database: Database) -> None:
        self._engine = database.engine

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        try:
            with self._engine.connect() as connection:
                yield connection
        except SQLAlchemyError as exc:
            # The type only: driver messages carry statement parameters, here personal data.
            logger.warning("visit storage unavailable: %s", type(exc).__name__)
            raise StorageUnavailable from None

    def create(self, scope: OwnedBy, draft: VisitDraft) -> Visit | NotPlanned:
        """The visit, owned by the scope's subject, for the customer `draft` names, which the
        same scope must select: another owner's customer is missing whatever its state, and only
        then is an own customer's archived state judged (scope before state). The state is read
        from the row the scoped statement selected, in the transaction that inserts the visit."""
        visit_id = new_identifier()
        with self._connection() as connection:
            selected = connection.execute(
                select(CustomerRow.archived_at.is_not(None)).where(
                    CustomerRow.id == draft.customer_id,
                    CustomerRow.owner_subject == scope.subject,
                )
            ).first()
            if selected is None:
                return NotPlanned.MISSING
            if selected[0]:
                return NotPlanned.ARCHIVED
            connection.execute(
                insert(VisitRow).values(
                    id=visit_id,
                    customer_id=draft.customer_id,
                    owner_subject=scope.subject,
                    starts_at=draft.starts_at,
                    ends_at=draft.ends_at,
                    own_address=draft.own_address,
                )
            )
            found = _find(connection, scope, visit_id)
            connection.commit()
        if found is None:
            # The row this transaction inserted, read back under the same scope.
            raise RuntimeError("a planned visit could not be read back")
        return found

    def find(self, scope: VisibilityScope, visit_id: uuid.UUID) -> Visit | None:
        """The visit by identifier and scope."""
        with self._connection() as connection:
            return _find(connection, scope, visit_id)

    def find_all(self, scope: VisibilityScope, period: Period | None) -> list[Visit]:
        """Every visit in the scope, or those whose start falls in the half-open `period`, the
        period's condition joined to the scope's by AND in one statement (ADR-0003 addendum of
        EKO-3-04). In start order, the identifier breaking ties so the answer is stable."""
        statement = _shown(scope).order_by(VisitRow.starts_at, VisitRow.id)
        if period is not None:
            statement = statement.where(
                VisitRow.starts_at >= period.starts, VisitRow.starts_at < period.ends
            )
        with self._connection() as connection:
            return [_visit(row) for row in connection.execute(statement).all()]
