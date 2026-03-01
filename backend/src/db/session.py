from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Get the URL from the environment (defined in docker-compose.yml)
# Default fallback is provided just in case
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:team20_password@db_vector:5432/ambience_knowledge",
)

# Create the engine
# pool_pre_ping=True checks if the connection is alive before using it
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create the Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency function to be used in API endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
