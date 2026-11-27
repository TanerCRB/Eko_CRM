"""Visits, the second owned record (EKO-4-01; expand only, a new table).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-26

Only creates a table no previous release names: nothing existing is altered or dropped, so the
previous release runs on this schema unchanged (ADR-0004 *Expand -> deploy -> contract*). Visit
identifiers are UUIDv4 values the application generates; no column has a sequence, an identity
or a default the database evaluates, so a restored backup set holds no counter that could issue
an identifier again (ADR-0006 *Visit identifiers are never reused*, ADR-0002-C13). No column holds
a visit state: Planned and Held are derived from `ends_at` at read time. `customer_id` is NOT
NULL with a foreign key and no cascading action (gate 1 A-4 A). Lock and statement timeouts come
from `migrate` (ADR-0004 addendum 2026-10-29), never from here.

ADR-0005 classification (ADR-0005-C1):
- `visit.id`: not personal data (an opaque identifier).
- `visit.customer_id`, `visit.owner_subject`, `visit.starts_at`, `visit.ends_at`: PD-C4 (the
  visit's customer and owner and its times).
- `visit.own_address`: PD-C2 (a visit's own address where one is given).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("owner_subject", sa.Text(collation="C"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("own_address", sa.Text(), nullable=True),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_visit_ends_after_start")),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
            name=op.f("fk_visit_customer_id_customer"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visit")),
    )
    op.create_index(op.f("ix_visit_customer_id"), "visit", ["customer_id"])
    op.create_index(op.f("ix_visit_starts_at"), "visit", ["starts_at"])
    op.create_index("ix_visit_owner_subject_starts_at", "visit", ["owner_subject", "starts_at"])


def downgrade() -> None:
    op.drop_index("ix_visit_owner_subject_starts_at", table_name="visit")
    op.drop_index(op.f("ix_visit_starts_at"), table_name="visit")
    op.drop_index(op.f("ix_visit_customer_id"), table_name="visit")
    op.drop_table("visit")
