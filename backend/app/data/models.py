"""Every mapped table is imported here, so Alembic's autogenerate and `alembic check` see it."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


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


__all__ = ["AppSession", "Base", "LoginTransaction", "SchemaRevisionLineage"]
