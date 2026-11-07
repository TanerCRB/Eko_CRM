"""Test-only revision (EKO-1-13 K-05, QA): raises Alembic's `CommandError` carrying a marker.

Alembic's command line catches `CommandError` itself and prints `FAILED: <message>`, so only the
`env.py` wrap stands between this message and the log; the interpreter hook never sees it. Never
under backend/migrations/versions/; it reaches a migrate run only through a test variant image
built FROM the shipped image (ADR-0004 addendum 2026-10-29).
"""

from collections.abc import Sequence

from alembic.util import CommandError

revision: str = "t_eko113_command_error"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Synthetic; the runtime test searches the log for it.
MARKER = "marker-k05-e113cmd"


def upgrade() -> None:
    raise CommandError(f"revision refused {MARKER}")


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
