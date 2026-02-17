from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class DatabaseManager:
    """Manager for database connections and operations."""

    def __init__(self):
        self.config = config.database
        self.engine = create_engine(self.config.connection_string)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_connection(self):
        """Get a raw psycopg2 connection."""
        return psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
        )

    def execute_query(
        self, query: str, params: Optional[tuple] = None
    ) -> list[dict[str, Any]]:
        """Execute a query and return results."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                return []

    def execute_many(self, query: str, params_list: list[tuple]) -> None:
        """Execute a query multiple times with different parameters."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
            conn.commit()

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    logger.info("Database connection successful")
                    return result is not None
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False


# Global database manager instance
db = DatabaseManager()
