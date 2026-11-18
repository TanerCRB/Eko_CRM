"""Customers and their contacts, the first product tables (EKO-3-01; expand only).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17

Only creates tables: nothing existing is altered or dropped, so the previous release runs on
this schema unchanged. Identifiers are UUIDv4 values the application generates; no column has a
sequence, an identity or a default evaluated by the database (ADR-0005-C17, ADR-0002-C13).

ADR-0005 classification (ADR-0005-C1):
- `customer.id`, `customer_contact.id`, `customer_contact.customer_id`,
  `customer_contact.position`: not personal data (opaque identifiers and an order).
- `customer.name`: PD-C1.
- `customer.country`, `customer_contact.kind`, `customer_contact.value`,
  `customer_contact.is_primary`: PD-C2.
- `customer_contact.note`: PD-C3.
- `customer.owner_subject`: PD-C4 (the owning rep's identity-server subject, stored as received,
  compared byte-wise; ADR-0003 *Identifier the application stores*).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(collation="C"), nullable=False),
        sa.Column("owner_subject", sa.Text(collation="C"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer")),
    )
    op.create_index(op.f("ix_customer_owner_subject"), "customer", ["owner_subject"])
    op.create_table(
        "customer_contact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(collation="C"), nullable=False),
        sa.Column("value", sa.Text(collation="C"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('phone', 'email')", name=op.f("ck_customer_contact_kind")),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
            name=op.f("fk_customer_contact_customer_id_customer"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_contact")),
        sa.UniqueConstraint(
            "customer_id", "position", name=op.f("uq_customer_contact_customer_id")
        ),
    )
    # At most one primary contact per customer, counted across kinds (CUS-1).
    op.create_index(
        "uq_customer_contact_one_primary",
        "customer_contact",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index("uq_customer_contact_one_primary", table_name="customer_contact")
    op.drop_table("customer_contact")
    op.drop_index(op.f("ix_customer_owner_subject"), table_name="customer")
    op.drop_table("customer")
