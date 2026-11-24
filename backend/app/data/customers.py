"""Customers and their contacts in PostgreSQL: the only module that reads or writes the owned
tables (ADR-0003 addendum of EKO-3-01, section 2; ADR-0003-C35).

Every function here takes the caller's scope as a required argument and applies it in the
statement that selects or writes the rows, so a customer outside the scope is never loaded and
"not visible" and "missing" are the same `None`. A create is one transaction: the customer and
all its contacts are written together or not at all. Identifiers are UUIDv4 values generated
here, never by a database sequence (ADR-0005-C17).

A taken NIP is decided by the database's unique constraint on `nip`, never by a read before the
insert (ADR-0002 *NIP uniqueness*; gate 1 of EKO-3-03): its violation, told apart by the
constraint's name, becomes `NipTaken`, which carries no value. The driver's message names the
NIP, so it is never read or written anywhere.
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from sqlalchemy import (
    ColumnElement,
    Connection,
    SQLColumnExpression,
    Text,
    bindparam,
    exists,
    func,
    insert,
    or_,
    select,
    true,
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
    TaxId,
)
from app.domain.ownership import AllRecords, OwnedBy, VisibilityScope

logger = logging.getLogger(__name__)


def new_identifier() -> uuid.UUID:
    """A random (version 4) identifier: no state a restore could rewind."""
    return uuid.uuid4()


# The customer's own columns at the head of a `find` row; the contact's follow.
CUSTOMER_COLUMNS = 10


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
                        id=customer_id,
                        name=draft.name,
                        country=draft.country,
                        owner_subject=scope.subject,
                        street=draft.address.street,
                        postal_code=draft.address.postal_code,
                        town=draft.address.town,
                        voivodeship=draft.address.voivodeship,
                        county=draft.address.county,
                        nip=draft.tax_id.nip,
                        foreign_tax_id=draft.tax_id.foreign,
                    )
                )
            except IntegrityError as error:
                if _is_nip_taken(error):
                    # Leaving the block rolls the transaction back: nothing of this create stays.
                    raise NipTaken from None
                raise
            if draft.contacts:
                connection.execute(
                    insert(CustomerContactRow),
                    [
                        {
                            "id": new_identifier(),
                            "customer_id": customer_id,
                            "position": position,
                            "kind": contact.kind.value,
                            "value": contact.value,
                            "note": contact.note,
                            "is_primary": contact.primary,
                        }
                        for position, contact in enumerate(draft.contacts)
                    ],
                )
            connection.commit()
        return Customer(
            customer_id, draft.name, draft.country, draft.contacts, draft.address, draft.tax_id
        )

    def find_by_nip(self, scope: VisibilityScope, nip: str) -> uuid.UUID | None:
        """The identifier, and nothing else, of the customer in the scope holding `nip`. Read
        after a create was refused for that NIP, in a transaction of its own, so the stored
        customer that refused it is committed and seen (gate 1 of EKO-3-03, A-3 A)."""
        statement = select(CustomerRow.id).where(CustomerRow.nip == nip, _visible(scope))
        with self._connection() as connection:
            found: uuid.UUID | None = connection.execute(statement).scalar_one_or_none()
        return found

    def find(self, scope: VisibilityScope, customer_id: uuid.UUID) -> Customer | None:
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
                CustomerContactRow.kind,
                CustomerContactRow.value,
                CustomerContactRow.note,
                CustomerContactRow.is_primary,
            )
            .outerjoin(CustomerContactRow, CustomerContactRow.customer_id == CustomerRow.id)
            .where(CustomerRow.id == customer_id, _visible(scope))
            .order_by(CustomerContactRow.position)
        )
        with self._connection() as connection:
            rows = connection.execute(statement).all()
        if not rows:
            return None
        found_id, name, country, *place, nip, foreign = rows[0][:CUSTOMER_COLUMNS]
        contacts = tuple(
            Contact(ContactKind(kind), value, note, primary)
            for kind, value, note, primary in (row[CUSTOMER_COLUMNS:] for row in rows)
            if kind is not None
        )
        return Customer(found_id, name, country, contacts, Address(*place), TaxId(nip, foreign))

    def find_all(self, scope: VisibilityScope, search: CustomerSearch) -> list[CustomerSummary]:
        """Every customer in the scope that the search selects, in one statement: the owner
        filter and the term only add conditions to the scope's, joined by AND (ADR-0003 addendum
        of EKO-3-04). The term matches the name, the town or a contact value, never a note.
        Ordered by identifier only so the answer is stable."""
        statement = (
            select(CustomerRow.id, CustomerRow.name, CustomerRow.country)
            .where(_visible(scope))
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
