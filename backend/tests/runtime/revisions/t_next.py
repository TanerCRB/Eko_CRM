"""Test-only revision (EKO-1-11): the next release's expand revision on top of the shipped head.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t_next"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TABLE eko_test_next (id integer PRIMARY KEY)")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
