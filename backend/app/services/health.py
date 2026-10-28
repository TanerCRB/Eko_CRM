from app.data.database import Database


def is_ready(database: Database) -> bool:
    """Readiness means the application database answers (ADR-0003-C23, G-2 A)."""
    return database.is_reachable()
