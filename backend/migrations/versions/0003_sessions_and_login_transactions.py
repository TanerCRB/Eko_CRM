"""Server-side sessions and login transactions (EKO-2-01; expand only).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12

ADR-0005 classification: every `app_session` column is PD-S3; `login_transaction` holds no
personal data. No column holds a staff e-mail address, username or credential (ADR-0003-C13), and
no column has a default evaluated by the database (ADR-0002-C13).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_session",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("session_hash", sa.Text(collation="C"), nullable=False),
        sa.Column("subject", sa.Text(collation="C"), nullable=False),
        sa.Column("tokens", sa.LargeBinary(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_session")),
        sa.UniqueConstraint("session_hash", name=op.f("uq_app_session_session_hash")),
    )
    op.create_index(op.f("ix_app_session_created_at"), "app_session", ["created_at"])
    op.create_table(
        "login_transaction",
        sa.Column("transaction_hash", sa.Text(collation="C"), nullable=False),
        sa.Column("state_hash", sa.Text(collation="C"), nullable=False),
        sa.Column("nonce_hash", sa.Text(collation="C"), nullable=False),
        sa.Column("verifier", sa.LargeBinary(), nullable=False),
        sa.Column("return_to", sa.Text(collation="C"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("transaction_hash", name=op.f("pk_login_transaction")),
    )
    op.create_index(
        op.f("ix_login_transaction_created_at"), "login_transaction", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_login_transaction_created_at"), table_name="login_transaction")
    op.drop_table("login_transaction")
    op.drop_index(op.f("ix_app_session_created_at"), table_name="app_session")
    op.drop_table("app_session")
