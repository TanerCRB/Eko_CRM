"""The unique constraint on `customer.nip` (EKO-3-03; a contract step, on a table holding rows).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-24

One unique constraint on `nip` and nothing else: NULLs stay distinct (PostgreSQL's default), so
any number of customers may have no Polish NIP, and `foreign_tax_id` gets none (ADR-0002 *NIP
uniqueness* and C9 as written, from this revision on). It ships with the code that answers a
duplicate, a declared deviation from ADR-0004 release step 3 accepted at gate 1 of EKO-3-03.

Before the DDL the revision counts, in SQL, the NIP values more than one customer holds; when
there are any it refuses the run naming only that count, and the run's one transaction rolls back
(G-2 A, G-6 A). No NIP is read into Python and no row is changed: duplicates are resolved by hand.
A duplicate stored after the count fails the DDL with a unique violation, which rolls back the
same way. Lock and statement timeouts come from `migrate` (ADR-0004 addendum 2026-10-29).

ADR-0005 classification (ADR-0005-C1): no new column; `customer.nip` stays PD-C1.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DUPLICATED_NIP_VALUES = sa.text(
    "SELECT count(*) FROM (SELECT nip FROM customer WHERE nip IS NOT NULL "
    "GROUP BY nip HAVING count(*) > 1) AS duplicated"
)


def upgrade() -> None:
    duplicated = op.get_bind().execute(DUPLICATED_NIP_VALUES).scalar_one()
    if duplicated:
        raise SystemExit(
            "migrate refused: revision 0007 needs every NIP unique; "
            f"NIP values held by more than one customer: {duplicated}"
        )
    op.create_unique_constraint(op.f("uq_customer_nip"), "customer", ["nip"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_customer_nip"), "customer", type_="unique")
