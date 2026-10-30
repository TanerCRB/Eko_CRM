"""Test-only revision (EKO-1-11): the same second revision with only its failing statement removed.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t_c14_second"
down_revision: str | None = "t_c14_first"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TABLE eko_test_c14_second (id integer PRIMARY KEY)")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
