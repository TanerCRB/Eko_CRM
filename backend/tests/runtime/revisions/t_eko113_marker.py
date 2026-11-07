"""Test-only revision (EKO-1-13 K-05): fails on a statement whose bound parameter is a marker.

The server cannot cast the marker, so the driver's error, and SQLAlchemy's wrapper with its
`[SQL: …]` and `[parameters: …]`, both carry it. Never under backend/migrations/versions/; it
reaches a migrate run only through a test variant image built FROM the shipped image (ADR-0004
addendum 2026-10-29).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t_eko113_marker"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Synthetic; the runtime test searches the log for it.
MARKER = "marker-k05-e113rev"


def upgrade() -> None:
    op.execute(sa.text("SELECT CAST(:v AS integer)").bindparams(v=MARKER))


def downgrade() -> None:
    raise NotImplementedError("test-only revisions are never downgraded")
