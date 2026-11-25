"""Customers and their contacts in PostgreSQL: the only module that reads or writes the owned
tables (ADR-0003 addendum of EKO-3-01, section 2; ADR-0003-C35).

Every function here takes the caller's scope as a required argument and applies it in the
statement that selects or writes the rows, so a customer outside the scope is never loaded and
"not visible" and "missing" are the same `None`. A create is one transaction: the customer and
all its contacts are written together or not at all. Identifiers are UUIDv4 values generated
here, never by a database sequence (ADR-0005-C17).

A change (EKO-3-05: edit, archive, restore) is one transaction too, and its `UPDATE` carries the
scope, the identifier and the state the change needs, so the state is judged on the row the
scoped statement locks: a change never lands on a customer whose state changed before the write
(ADR-0003 addendum draft of EKO-3-05, Q-3 A). Contacts are replaced only through the identifier
that scoped `UPDATE` returned. No change writes `owner_subject`.

A taken NIP is decided by the database's unique constraint on `nip`, never by a read before the
insert or the update (ADR-0002 *NIP uniqueness*; gate 1 of EKO-3-03; ADR-0003-C40): its
violation, told apart by the constraint's name, becomes `NipTaken`, which carries no value. The
driver's message names the NIP, so it is never read or written anywhere.
"""

import logging
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime

import psycopg
from sqlalchemy import (
    ColumnElement,
    Connection,
    SQLColumnExpression,
    Text,
    bindparam,
    delete,
    exists,
    func,
    insert,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.data.database import Database
from app.data.models import NIP_UNIQUE, CustomerContactRow, CustomerRow
from app.data.sessions import StorageUnavailable
from app.domain.customers import (
    Address,
    Contact,
    ContactKind,
    Customer,
    CustomerDraft,
    CustomerSearch,
    CustomerSummary,
    NipTaken,
    StateFilter,
    TaxId,
    Unchanged,
)
from app.domain.ownership import AllRecords, OwnedBy, VisibilityScope

logger = logging.getLogger(__name__)


def new_identifier() -> uuid.UUID:
    """A random (version 4) identifier: no state a restore could rewind."""
    return uuid.uuid4()


# The customer's own columns at the head of a `find` row; the contact's follow.
CUSTOMER_COLUMNS = 11


# ADR-0002 addendum of EKO-3-04: case is ignored by the builtin provider's folding, the same for
# every searched column whatever its own collation, never by ICU.
FOLDING_COLLATION = "pg_unicode_fast"
LIKE_ESCAPE = "\\"


def _folded(value: SQLColumnExpression[str | None]) -> ColumnElement[str]:
    return func.casefold(value.collate(FOLDING_COLLATION), type_=Text)


def _contains(
    value: SQLColumnExpression[str | None], pattern: SQLColumnExpression[str]
) -> ColumnElement[bool]:
    """A NULL value (a customer with no town) is no match, never an error."""
    return _folded(value).like(_folded(pattern), escape=LIKE_ESCAPE)


def like_pattern(term: str) -> str:
    """`term` anywhere, every pattern character in it taken literally."""
    for special in (LIKE_ESCAPE, "%", "_"):
        term = term.replace(special, LIKE_ESCAPE + special)
    return f"%{term}%"


def _visible(scope: VisibilityScope) -> ColumnElement[bool]:
    if isinstance(scope, AllRecords):
        return true()
    return CustomerRow.owner_subject == scope.subject


# The stored state as the answers carry it: NULL is active (revision 0008, Q-4 B).
ARCHIVED = CustomerRow.archived_at.is_not(None)
# The list's state condition, joined to the scope's by AND; `both` drops only this one.
STATE_CONDITIONS: dict[StateFilter, ColumnElement[bool]] = {
    StateFilter.ACTIVE: CustomerRow.archived_at.is_(None),
    StateFilter.ARCHIVED: ARCHIVED,
    StateFilter.BOTH: true(),
}


def _draft_columns(draft: CustomerDraft) -> dict[str, str | None]:
    """The columns a customer request states: never the owner, never the archived state."""
    return {
        "name": draft.name,
        "country": draft.country,
        "street": draft.address.street,
        "postal_code": draft.address.postal_code,
        "town": draft.address.town,
        "voivodeship": draft.address.voivodeship,
        "county": draft.address.county,
        "nip": draft.tax_id.nip,
        "foreign_tax_id": draft.tax_id.foreign,
    }


def _contact_rows(customer_id: uuid.UUID, contacts: Sequence[Contact]) -> list[dict[str, object]]:
    """The contact rows of one customer in the order given, each with a new identifier."""
    return [
        {
            "id": new_identifier(),
            "customer_id": customer_id,
            "position": position,
            "kind": contact.kind.value,
            "value": contact.value,
            "note": contact.note,
            "is_primary": contact.primary,
        }
        for position, contact in enumerate(contacts)
    ]


def _find(
    connection: Connection, scope: VisibilityScope, customer_id: uuid.UUID
) -> Customer | None:
    """One statement: the customer by identifier and scope, with its contacts in order."""
    statement = (
        select(
            CustomerRow.id,
            CustomerRow.name,
            CustomerRow.country,
            CustomerRow.street,
            CustomerRow.postal_code,
            CustomerRow.town,
            CustomerRow.voivodeship,
            CustomerRow.county,
            CustomerRow.nip,
            CustomerRow.foreign_tax_id,
            ARCHIVED,
            CustomerContactRow.kind,
            CustomerContactRow.value,
            CustomerContactRow.note,
            CustomerContactRow.is_primary,
        )
        .outerjoin(CustomerContactRow, CustomerContactRow.customer_id == CustomerRow.id)
        .where(CustomerRow.id == customer_id, _visible(scope))
        .order_by(CustomerContactRow.position)
    )
    rows = connection.execute(statement).all()
    if not rows:
        return None
    found_id, name, country, *place, nip, foreign, archived = rows[0][:CUSTOMER_COLUMNS]
    contacts = tuple(
        Contact(ContactKind(kind), value, note, primary)
        for kind, value, note, primary in (row[CUSTOMER_COLUMNS:] for row in rows)
        if kind is not None
    )
    return Customer(
        found_id, name, country, contacts, Address(*place), TaxId(nip, foreign), archived=archived
    )


def _unchanged(connection: Connection, scope: VisibilityScope, customer_id: uuid.UUID) -> Unchanged:
    """Why a scoped `UPDATE` wrote nothing, asked under the same scope: a customer outside it is
    missing whatever its state (scope before state)."""
    inside = connection.execute(
        select(CustomerRow.id).where(CustomerRow.id == customer_id, _visible(scope))
    ).first()
    # Inside the scope, the row failed only the state condition: it was archived when written.
    return Unchanged.MISSING if inside is None else Unchanged.ARCHIVED


def _is_nip_taken(error: IntegrityError) -> bool:
    """Whether the violated constraint is the one on `nip`, from the driver's diagnostic field:
    SQLSTATE 23505 alone is not enough, the contact table's one-primary index raises it too."""
    cause = error.orig
    return (
        isinstance(cause, psycopg.errors.UniqueViolation)
        and cause.diag.constraint_name == NIP_UNIQUE
    )


class CustomerStore:
    def __init__(self, database: Database) -> None:
        self._engine = database.engine

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        try:
            with self._engine.connect() as connection:
                yield connection
        except SQLAlchemyError as exc:
            # The type only: driver messages carry statement parameters, here personal data.
            logger.warning("customer storage unavailable: %s", type(exc).__name__)
            raise StorageUnavailable from None

    def create(self, scope: OwnedBy, draft: CustomerDraft) -> Customer:
        """The customer, owned by the scope's subject, and its contacts in the order given."""
        customer_id = new_identifier()
        with self._connection() as connection:
            try:
                connection.execute(
                    insert(CustomerRow).values(
                        id=customer_id, owner_subject=scope.subject, **_draft_columns(draft)
                    )
                )
            except IntegrityError as error:
                if _is_nip_taken(error):
                    # Leaving the block rolls the transaction back: nothing of this create stays.
                    raise NipTaken from None
                raise
            if draft.contacts:
                rows = _contact_rows(customer_id, draft.contacts)
                connection.execute(insert(CustomerContactRow), rows)
            connection.commit()
        return Customer(
            customer_id,
            draft.name,
            draft.country,
            draft.contacts,
            draft.address,
            draft.tax_id,
            archived=False,
        )

    def find_by_nip(self, scope: VisibilityScope, nip: str) -> uuid.UUID | None:
        """The identifier, and nothing else, of the customer in the scope holding `nip`. Read
        after a create or an edit was refused for that NIP, in a transaction of its own, so the
        stored customer that refused it is committed and seen (gate 1 of EKO-3-03, A-3 A)."""
        statement = select(CustomerRow.id).where(CustomerRow.nip == nip, _visible(scope))
        with self._connection() as connection:
            found: uuid.UUID | None = connection.execute(statement).scalar_one_or_none()
        return found

    def find(self, scope: VisibilityScope, customer_id: uuid.UUID) -> Customer | None:
        """The customer by identifier and scope, with its contacts in order."""
        with self._connection() as connection:
            return _find(connection, scope, customer_id)

    def edit(
        self, scope: VisibilityScope, customer_id: uuid.UUID, draft: CustomerDraft
    ) -> Customer | Unchanged:
        """The whole customer as `draft` states it, its contacts replaced in the order given, in
        one transaction (G-5 A, G-6 A); only an active customer is edited (G-4 A). The owner is
        the stored one: the `UPDATE` does not name it. A NIP another customer holds is refused
        by the constraint on that `UPDATE`, as on create (C40); the target keeps its own."""
        with self._connection() as connection:
            try:
                written = connection.execute(
                    update(CustomerRow)
                    .where(
                        CustomerRow.id == customer_id,
                        _visible(scope),
                        CustomerRow.archived_at.is_(None),
                    )
                    .values(**_draft_columns(draft))
                    .returning(CustomerRow.id)
                ).scalar_one_or_none()
            except IntegrityError as error:
                # Reached only by a row the scope and the state let through (ADR-0003-C40);
                # leaving the block rolls the edit back, its contacts untouched.
                if _is_nip_taken(error):
                    raise NipTaken from None
                raise
            if written is None:
                return _unchanged(connection, scope, customer_id)
            connection.execute(
                delete(CustomerContactRow).where(CustomerContactRow.customer_id == written)
            )
            if draft.contacts:
                rows = _contact_rows(written, draft.contacts)
                connection.execute(insert(CustomerContactRow), rows)
            found = _find(connection, scope, written)
            connection.commit()
        if found is None:
            # The row the scoped UPDATE wrote, read back under the same scope and transaction.
            raise RuntimeError("an edited customer could not be read back")
        return found

    def archive(
        self, scope: VisibilityScope, customer_id: uuid.UUID, at: datetime
    ) -> Customer | None:
        """The customer archived at `at`. One already archived keeps its row, its instant
        included, so a repeat changes nothing (K-04); nothing else of the row is written."""
        if at.utcoffset() is None:
            raise ValueError("an instant needs its offset")
        with self._connection() as connection:
            connection.execute(
                update(CustomerRow)
                .where(
                    CustomerRow.id == customer_id,
                    _visible(scope),
                    CustomerRow.archived_at.is_(None),
                )
                .values(archived_at=at)
            )
            found = _find(connection, scope, customer_id)
            connection.commit()
        return found

    def restore(self, scope: VisibilityScope, customer_id: uuid.UUID) -> Customer | None:
        """The customer active again. One already active keeps its row, so a repeat changes
        nothing (K-04); nothing else of the row is written."""
        with self._connection() as connection:
            connection.execute(
                update(CustomerRow)
                .where(
                    CustomerRow.id == customer_id,
                    _visible(scope),
                    CustomerRow.archived_at.is_not(None),
                )
                .values(archived_at=None)
            )
            found = _find(connection, scope, customer_id)
            connection.commit()
        return found

    def find_all(self, scope: VisibilityScope, search: CustomerSearch) -> list[CustomerSummary]:
        """Every customer in the scope that the search selects, in one statement: the owner
        filter, the term and the state only add conditions to the scope's, joined by AND
        (ADR-0003 addenda of EKO-3-04 and EKO-3-05). The term matches the name, the town or a
        contact value, never a note. Ordered by identifier only so the answer is stable."""
        statement = (
            select(CustomerRow.id, CustomerRow.name, CustomerRow.country, ARCHIVED)
            .where(_visible(scope), STATE_CONDITIONS[search.state])
            .order_by(CustomerRow.id)
        )
        if search.owner is not None:
            statement = statement.where(CustomerRow.owner_subject == search.owner)
        if search.term is not None:
            pattern = bindparam("pattern", like_pattern(search.term), type_=Text)
            contact = (
                exists()
                .where(CustomerContactRow.customer_id == CustomerRow.id)
                .where(_contains(CustomerContactRow.value, pattern))
            )
            statement = statement.where(
                or_(
                    _contains(CustomerRow.name, pattern),
                    _contains(CustomerRow.town, pattern),
                    contact,
                )
            )
        with self._connection() as connection:
            return [CustomerSummary(*row) for row in connection.execute(statement).all()]
