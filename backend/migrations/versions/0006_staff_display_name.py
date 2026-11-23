"""The staff display-name copy (EKO-3-08; expand only, a new table).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-23

A new table no previous release names, with no foreign key to `customer`, so the previous
release runs unchanged against it. One row per subject, written by the login callback; no column
has a default evaluated by the database (ADR-0002-C13), and no column holds a staff e-mail address,
username or credential (ADR-0003-C13). Lock and statement timeouts come from `migrate` (ADR-0004
addendum 2026-10-29), never from here.

ADR-0005 classification (ADR-0005-C1; PD-S3 as extended by the EKO-3-08 addendum):
- `staff_display_name.subject`: PD-S3 (the staff member's subject identifier).
- `staff_display_name.display_name`: PD-S3 (the display-name copy, given and family name).
- `staff_display_name.is_rep`: PD-S3 (whether the token of the last login held `rep`).
- `staff_display_name.last_login_at`: PD-S3 (the instant of the last login).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_display_name",
        sa.Column("subject", sa.Text(collation="C"), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("is_rep", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("subject", name=op.f("pk_staff_display_name")),
    )
    op.create_index(
        op.f("ix_staff_display_name_last_login_at"), "staff_display_name", ["last_login_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_staff_display_name_last_login_at"), table_name="staff_display_name")
    op.drop_table("staff_display_name")
