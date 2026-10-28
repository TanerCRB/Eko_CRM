"""Every mapped table is imported here, so Alembic's autogenerate and `alembic check` see it.

The walking skeleton maps no table yet.
"""

from app.data.base import Base

__all__ = ["Base"]
