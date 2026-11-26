"""The dataset key of a customer the operator seed loads (EKO-3-06; expand only, on a table holding
rows).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25

One nullable column without a default and its unique index (gate 1 of EKO-3-06, A-2 A): no
existing row is rewritten, and the previous release, which names neither, reads and inserts
customers unchanged. Only the operator seed writes the column; every customer a request creates
keeps it NULL, and NULLs stay distinct. The index decides in the seed's insert whether a record is
already loaded. Lock and statement timeouts come from `migrate` (ADR-0004 addendum 2026-10-29).

ADR-0005 classification (ADR-0005-C1):
- `customer.dataset_key`: not personal data (an opaque index into the committed synthetic
  dataset, derived from no field value).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("dataset_key", sa.Text(collation="C"), nullable=True))
    op.create_index(op.f("uq_customer_dataset_key"), "customer", ["dataset_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("uq_customer_dataset_key"), table_name="customer")
    op.drop_column("customer", "dataset_key")
