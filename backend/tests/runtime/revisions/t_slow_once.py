"""Test-only revision (EKO-1-11): slow, and leaves one trace per execution.

The sequence eko_test_trace is created by the test before the runs; nextval survives a rollback,
so its value counts every execution of this upgrade, committed or not.

Never under backend/migrations/versions/; it reaches a migrate run only through a test variant
image built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t_slow_once"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SELECT nextval('eko_test_trace')")
    op.execute("CREATE TABLE eko_test_slow_once (id integer PRIMARY KEY)")
    op.execute("SELECT pg_sleep(8)")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
