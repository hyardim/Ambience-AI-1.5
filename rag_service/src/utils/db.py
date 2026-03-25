from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import cast

from psycopg2.extensions import connection as PsycopgConnection
from psycopg2.pool import ThreadedConnectionPool
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import db_config
from .logger import setup_logger

logger = setup_logger(__name__)


class DatabaseManager:
    """Manager for database connections and operations.

    Uses SQLAlchemy for standard CRUD operations and raw psycopg2
    for vector similarity searches where ORM conventions get in the way.
    """

    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._session_local: sessionmaker[Session] | None = None
        self._raw_pool: ThreadedConnectionPool | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                db_config.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
        return self._engine

    @property
    def SessionLocal(self) -> sessionmaker[Session]:
        if self._session_local is None:
            self._session_local = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
            )
        return self._session_local

    def get_session(self) -> Session:
        """Get a SQLAlchemy session for standard operations."""
        return cast(Session, self.SessionLocal())

    @property
    def raw_pool(self) -> ThreadedConnectionPool:
        if self._raw_pool is None:
            self._raw_pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=db_config.database_url,
            )
        return self._raw_pool

    def get_raw_connection(self) -> PsycopgConnection:
        """Get a pooled raw psycopg2 connection for vector search queries."""
        return cast(PsycopgConnection, self.raw_pool.getconn())

    def release_raw_connection(self, conn: PsycopgConnection) -> None:
        """Return a pooled raw connection back to the pool."""
        try:
            self.raw_pool.putconn(conn)
        except Exception:
            with suppress(Exception):
                conn.close()

    @contextmanager
    def raw_connection(self) -> Iterator[PsycopgConnection]:
        """Yield a pooled psycopg2 connection and return it safely afterwards."""
        conn = self.get_raw_connection()
        try:
            yield conn
        finally:
            self.release_raw_connection(conn)

    def test_connection(self) -> bool:
        """Test database is reachable."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False


# Global instance - engine is only created when first accessed
db = DatabaseManager()
