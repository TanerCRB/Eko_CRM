"""Every mapped table is imported here, so Alembic's autogenerate and `alembic check` see it."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class SchemaRevisionLineage(Base):
    """The revisions from the base to the database's head; written only by migrate (revision 0002,
    ADR-0004 addendum 2026-10-29). No column default: no value read from the database clock."""

    __tablename__ = "schema_revision_lineage"

    # Collation "C": revision identifiers compare byte-wise.
    revision: Mapped[str] = mapped_column(Text(collation="C"), primary_key=True)


__all__ = ["Base", "SchemaRevisionLineage"]
