"""Test-only revision (EKO-1-11): the same statement, shortened below the statement timeout.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t_sleep_25"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SELECT pg_sleep(25)")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
