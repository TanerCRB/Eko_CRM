"""The customer's archived state (EKO-3-05; expand only, on a table holding rows).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-24

Adds one nullable column without a default (gate-1 decision Q-4 B): NULL is an active customer,
so no existing row is rewritten, every existing customer is active after the step, and an
`INSERT` by the previous release, which names no such column, stores an active customer (ADR-0004
addendum draft of EKO-3-05). The instant is written only by the application, from its clock,
never by a database default (ADR-0002-C13). Lock and statement timeouts come from `migrate`
(ADR-0004 addendum 2026-10-29), never from here.

ADR-0005 classification (ADR-0005-C1):
- `customer.archived_at`: PD-C4 (the customer's archived state).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("customer", "archived_at")
