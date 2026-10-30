"""The revision lineage record migrate writes, so a newer revision can be placed (expand).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_revision_lineage",
        sa.Column("revision", sa.Text(collation="C"), nullable=False),
        sa.PrimaryKeyConstraint("revision", name=op.f("pk_schema_revision_lineage")),
    )


def downgrade() -> None:
    op.drop_table("schema_revision_lineage")
