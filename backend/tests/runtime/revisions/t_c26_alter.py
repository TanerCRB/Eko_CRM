"""Test-only revision (EKO-1-11): an expand revision altering a table that reps' requests read.

The table eko_test_contended is created by the test, owned by the application role.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t_c26_alter"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE eko_test_contended ADD COLUMN note integer")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
