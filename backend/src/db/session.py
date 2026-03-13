from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import os

# Get the URL from the environment (defined in docker-compose.yml)
# Default fallback is provided just in case
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:team20_password@db_vector:5432/ambience_knowledge",
)

# ---------------------------------------------------------------------------
# Synchronous engine & session (used by all non-chat routes)
# ---------------------------------------------------------------------------
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Async engine & session (used by the chat/RAG generation path)
# ---------------------------------------------------------------------------

def _make_async_url(url: str) -> str:
    """Convert a psycopg2 / plain postgresql URL to an asyncpg URL."""
    if url.startswith("sqlite"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


ASYNC_DATABASE_URL = _make_async_url(DATABASE_URL)

async_engine = create_async_engine(ASYNC_DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_db():
    """FastAPI dependency that yields an AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
