"""Engine construction and the readiness probe: the only database access the skeleton has."""

import logging

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import Settings

logger = logging.getLogger(__name__)


def database_url(settings: Settings) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=settings.app_db_user,
        password=settings.app_db_password.get_secret_value(),
        host=settings.app_db_host,
        port=settings.app_db_port,
        database=settings.app_db_name,
    )


def connect_args(settings: Settings) -> dict[str, object]:
    # Session time zone UTC for every application connection (ADR-0002).
    return {
        "connect_timeout": settings.app_db_connect_timeout_seconds,
        "options": "-c timezone=UTC",
    }


def create_app_engine(settings: Settings) -> Engine:
    return create_engine(
        database_url(settings),
        pool_size=settings.app_db_pool_size,
        max_overflow=settings.app_db_max_overflow,
        pool_pre_ping=True,
        connect_args=connect_args(settings),
    )


class Database:
    """The application database as the layers above `data` see it: no SQLAlchemy type leaks out."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        return cls(create_app_engine(settings))

    def is_reachable(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            # The type only: driver messages name hosts and roles.
            logger.warning("database unreachable: %s", type(exc).__name__)
            return False
        return True

    def dispose(self) -> None:
        self._engine.dispose()
