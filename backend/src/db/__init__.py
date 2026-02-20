import os
import psycopg2


def get_conn():
    """
    Establishes a connection to the PostgreSQL database.
    Now updated with Team 20 credentials.
    """
    try:
        # We prefer the DATABASE_URL if it exists (Docker provides this),
        # otherwise we fall back to the explicit Team 20 credentials.
        db_url = os.getenv("DATABASE_URL")

        if db_url:
            conn = psycopg2.connect(db_url)
        else:
            conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "db_vector"),
                user=os.getenv("POSTGRES_USER", "admin"),
                password=os.getenv("POSTGRES_PASSWORD", "team20_password"),
                dbname=os.getenv("POSTGRES_DB", "ambience_knowledge"),
            )
        return conn
    except Exception as e:
        print(f"❌ Database Connection Failed: {e}")
        return None
