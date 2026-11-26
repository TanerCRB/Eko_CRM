"""Every mapped table is imported here, so Alembic's autogenerate and `alembic check` see it."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base

NIP_UNIQUE = "uq_customer_nip"
DATASET_KEY_UNIQUE = "uq_customer_dataset_key"


class SchemaRevisionLineage(Base):
    """The revisions from the base to the database's head; written only by migrate (revision 0002,
    ADR-0004 addendum 2026-10-29). No column default: no value read from the database clock."""

    __tablename__ = "schema_revision_lineage"

    # Collation "C": revision identifiers compare byte-wise.
    revision: Mapped[str] = mapped_column(Text(collation="C"), primary_key=True)


class AppSession(Base):
    """A server-side browser session (ADR-0003 *Browser flow*); every column is PD-S3 (ADR-0005).

    Revision 0003. No column default: every instant comes from the application's clock.
    """

    __tablename__ = "app_session"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # SHA-256 of the cookie's identifier; the identifier itself is never stored.
    session_hash: Mapped[str] = mapped_column(Text(collation="C"), unique=True)
    # The identity server's `sub`, compared exactly (ADR-0003 *Identifier the application stores*).
    subject: Mapped[str] = mapped_column(Text(collation="C"))
    # Access, refresh and ID token, sealed together by `auth` (AES-256-GCM).
    tokens: Mapped[bytes] = mapped_column(LargeBinary)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginTransaction(Base):
    """A login between its start and its callback; no personal data (ADR-0005). Revision 0003."""

    __tablename__ = "login_transaction"

    # SHA-256 of the transaction cookie's identifier.
    transaction_hash: Mapped[str] = mapped_column(Text(collation="C"), primary_key=True)
    state_hash: Mapped[str] = mapped_column(Text(collation="C"))
    nonce_hash: Mapped[str] = mapped_column(Text(collation="C"))
    # The PKCE verifier, sealed by `auth`.
    verifier: Mapped[bytes] = mapped_column(LargeBinary)
    # A path of the single-page application; opaque identifiers only (ADR-0005).
    return_to: Mapped[str] = mapped_column(Text(collation="C"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StaffDisplayNameRow(Base):
    """The staff display-name copy (ADR-0003 *Staff display name* A, ADR-0003-C37); every column is
    PD-S3 (ADR-0005, as extended by the EKO-3-08 addendum). Revision 0006. Not an owned table.

    Written only by the login callback, in the transaction that creates the session; deleted only
    by the retention run. No column default: the instant comes from the application's clock.
    """

    __tablename__ = "staff_display_name"

    # The identity server's `sub`, stored as received and compared byte-wise.
    subject: Mapped[str] = mapped_column(Text(collation="C"), primary_key=True)
    # The verified access token's `name` in NFC, not trimmed; NULL when the token carries none.
    display_name: Mapped[str | None] = mapped_column(Text)
    # Whether that login's token held `rep`; it only selects the entries of the list of reps.
    is_rep: Mapped[bool] = mapped_column(Boolean)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CustomerRow(Base):
    """A rep's customer (CUS-1, CUS-2); an owned table (ADR-0003 addendum of EKO-3-01). Revision
    0004. Read and changed only through `app.data.customers`, under a visibility scope.

    `id` is a UUIDv4 the application generates: no sequence, so a restore cannot make an
    identifier be issued twice (ADR-0005-C17).
    """

    __tablename__ = "customer"
    __table_args__ = (
        # Only the canonical ten digits (ADR-0002 *NIP uniqueness*).
        CheckConstraint("nip ~ '^[0-9]{10}$'", name="nip"),
        # Company-wide, NULLs distinct; revision 0007 (EKO-3-03). `app.data.customers` tells its
        # violation apart by this name.
        UniqueConstraint("nip", name=NIP_UNIQUE),
        # Revision 0008 (EKO-3-06): decides in the seed's insert whether a record is loaded.
        Index(DATASET_KEY_UNIQUE, "dataset_key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # NFC, trimmed, at most 120 characters (ADR-0002, G-1 A); PD-C1.
    name: Mapped[str] = mapped_column(Text)
    # A code from a closed list, compared byte-wise (G-3 A).
    country: Mapped[str] = mapped_column(Text(collation="C"))
    # The creating rep's subject, stored as received and compared exactly (ADR-0003).
    owner_subject: Mapped[str] = mapped_column(Text(collation="C"), index=True)
    # Revision 0005 (EKO-3-02): the address and the tax identifier, NULL when not given (G-2 A).
    street: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    town: Mapped[str | None] = mapped_column(Text)
    # Exactly as the dated TERYT file names them, Polish customers only (Q-4 A, C-3 A).
    voivodeship: Mapped[str | None] = mapped_column(Text)
    county: Mapped[str | None] = mapped_column(Text)
    # A Polish customer's NIP, ten digits; never a foreign value.
    nip: Mapped[str | None] = mapped_column(Text(collation="C"))
    # Any other customer's tax identifier as entered, trimmed and NFC.
    foreign_tax_id: Mapped[str | None] = mapped_column(Text)
    # Revision 0008 (EKO-3-06): a seeded record's key in the committed dataset, written only by
    # the operator seed; NULL for every customer a request creates. Not personal data.
    dataset_key: Mapped[str | None] = mapped_column(Text(collation="C"))
    # Revision 0009 (EKO-3-05, Q-4 B): when the customer was archived, NULL while it is active;
    # PD-C4. Set only from the application's clock, never by a column default (ADR-0002-C13).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerContactRow(Base):
    """One phone or e-mail of a customer, reached only through its customer; it carries no owner
    of its own (ADR-0003 addendum of EKO-3-01). Revision 0004."""

    __tablename__ = "customer_contact"
    __table_args__ = (
        CheckConstraint("kind IN ('phone', 'email')", name="kind"),
        UniqueConstraint("customer_id", "position"),
        # At most one primary contact per customer, counted across kinds (CUS-1).
        Index(
            "uq_customer_contact_one_primary",
            "customer_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customer.id"))
    # The contact's place in the order it was sent (G-6 A).
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text(collation="C"))
    # A phone in E.164 form, or an e-mail address as entered and trimmed (CUS-8, G-3 A).
    value: Mapped[str] = mapped_column(Text(collation="C"))
    # Who the contact reaches; NULL when there is none (G-4 A).
    note: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean)


__all__ = [
    "AppSession",
    "Base",
    "CustomerContactRow",
    "CustomerRow",
    "LoginTransaction",
    "SchemaRevisionLineage",
    "StaffDisplayNameRow",
]
