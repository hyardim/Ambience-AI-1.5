import psycopg2
from sqlalchemy import create_engine, text
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
        self.engine = create_engine(
            db_config.connection_string,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
        )

    def get_session(self) -> Session:
        """Get a SQLAlchemy session for standard operations."""
        return self.SessionLocal()

    def get_raw_connection(self) -> psycopg2.extensions.connection:
        """Get a raw psycopg2 connection for vector search queries."""
        return psycopg2.connect(
            host=db_config.postgres_host,
            port=db_config.postgres_port,
            dbname=db_config.postgres_db,
            user=db_config.postgres_user,
            password=db_config.postgres_password,
        )

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


# Global instance - import and use anywhere
db = DatabaseManager()
