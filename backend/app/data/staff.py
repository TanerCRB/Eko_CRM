"""The staff display-name copy in PostgreSQL: the manager's list of reps and the copy's retention
(EKO-3-08). The copy is written by `app.data.sessions` in the login's own transaction
(ADR-0003-C37).

The copy table is not an owned table (ADR-0003 addendum of EKO-3-08), so its reads take no
visibility scope; who may call them is the route's manager check. The retention's deletion is the
one function on ADR-0003-C35's closed system-read list: it reads the owned tables only to test
whether a row of the reference set refers to a subject, returns a count, and no module under
`app.api` or `app.auth` reaches it.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Connection, delete, exists, func, not_, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.data.database import Database
from app.data.models import CustomerRow, StaffDisplayNameRow
from app.data.sessions import StorageUnavailable
from app.domain.staff import Rep

logger = logging.getLogger(__name__)

# ADR-0005 addendum of EKO-3-08: the columns whose subject keeps a copy. A column holding a staff
# subject is named `*_subject` and is added here in the release that adds it (ADR-0005-C20).
REFERENCE_SET = (CustomerRow.owner_subject,)


@contextmanager
def _connection(database: Database) -> Iterator[Connection]:
    try:
        with database.engine.connect() as connection:
            yield connection
    except SQLAlchemyError as exc:
        # The type only: driver messages carry statement parameters, here staff names.
        logger.warning("staff storage unavailable: %s", type(exc).__name__)
        raise StorageUnavailable from None


class StaffStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def reps(self) -> list[Rep]:
        """Every copy whose last login's token held `rep`; ordered by subject only so the answer
        is stable (G-6 A: the order shown is the SPA's)."""
        statement = (
            select(StaffDisplayNameRow.subject, StaffDisplayNameRow.display_name)
            .where(StaffDisplayNameRow.is_rep)
            .order_by(StaffDisplayNameRow.subject)
        )
        with _connection(self._database) as connection:
            return [Rep(subject, name) for subject, name in connection.execute(statement).all()]

    def earliest_login_after(self, logged_in_after: datetime) -> datetime | None:
        """The earliest last-login instant later than the given one, from the copy table alone.
        The retention asks for the copies not yet past their bound: one past it and still stored
        is referred to, so it is no reason to wake up."""
        statement = select(func.min(StaffDisplayNameRow.last_login_at)).where(
            StaffDisplayNameRow.last_login_at > logged_in_after
        )
        with _connection(self._database) as connection:
            earliest: datetime | None = connection.execute(statement).scalar_one()
        return earliest


def delete_unreferenced_copies(database: Database, logged_in_at_or_before: datetime) -> int:
    """Copies whose last login is at or before the instant and whose subject no column of the
    reference set holds; their count. On ADR-0003-C35's closed system-read list: the owned tables
    are read only inside `EXISTS`, and no column of theirs is returned."""
    referred_to = or_(
        *(exists().where(column == StaffDisplayNameRow.subject) for column in REFERENCE_SET)
    )
    statement = delete(StaffDisplayNameRow).where(
        StaffDisplayNameRow.last_login_at <= logged_in_at_or_before, not_(referred_to)
    )
    with _connection(database) as connection:
        deleted = connection.execute(statement).rowcount
        connection.commit()
    return int(deleted or 0)
