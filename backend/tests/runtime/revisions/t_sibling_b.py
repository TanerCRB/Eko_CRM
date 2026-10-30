"""Test-only revision (EKO-1-11): the other of two siblings on the shipped head.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t_sibling_b"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TABLE eko_test_sibling_b (id integer PRIMARY KEY)")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
