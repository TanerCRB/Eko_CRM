"""Test-only revision (EKO-1-11): a planted contrast, named like a real revision.

K-07: copied into a variant's migrations/versions it keeps one head, so a one-head check passes
while the shipped-tree check must fail.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TABLE eko_test_planted (id integer PRIMARY KEY)")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
