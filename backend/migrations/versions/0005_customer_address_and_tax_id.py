"""The customer's address and tax identifier (EKO-3-02; expand only, on a table holding rows).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19

Adds nullable columns without a default, so no existing row is rewritten or changed and the
previous release, which names none of them, reads and inserts customers unchanged. The one
constraint, on the new all-NULL `nip`, admits only ten digits (ADR-0002 *NIP uniqueness*); its
unique constraint is EKO-3-03's, a declared deviation accepted at gate 1 of EKO-3-02. Lock and
statement timeouts come from `migrate` (ADR-0004 addendum 2026-10-29), never from here.

ADR-0005 classification (ADR-0005-C1):
- `customer.nip`, `customer.foreign_tax_id`: PD-C1 (a sole trader's tax identifier).
- `customer.street`, `customer.postal_code`, `customer.town`, `customer.voivodeship`,
  `customer.county`: PD-C2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("street", sa.Text(), nullable=True))
    op.add_column("customer", sa.Column("postal_code", sa.Text(), nullable=True))
    op.add_column("customer", sa.Column("town", sa.Text(), nullable=True))
    op.add_column("customer", sa.Column("voivodeship", sa.Text(), nullable=True))
    op.add_column("customer", sa.Column("county", sa.Text(), nullable=True))
    op.add_column("customer", sa.Column("nip", sa.Text(collation="C"), nullable=True))
    op.add_column("customer", sa.Column("foreign_tax_id", sa.Text(), nullable=True))
    op.create_check_constraint(op.f("ck_customer_nip"), "customer", "nip ~ '^[0-9]{10}$'")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_customer_nip"), "customer", type_="check")
    for column in ("foreign_tax_id", "nip", "county", "voivodeship", "town", "postal_code"):
        op.drop_column("customer", column)
    op.drop_column("customer", "street")
