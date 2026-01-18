# We import psycopg2 to connect to Postgres.
import psycopg2

# We import psycopg2 extras so we can insert dictionaries easily and fetch rows neatly.
import psycopg2.extras

# Import our DATABASE_URL from config.
from .config import DATABASE_URL, HNSW_M, HNSW_EF_CONSTRUCTION

def get_conn():
    """
    Creates and returns a Postgres connection using DATABASE_URL.
    """
    # Connect to Postgres with psycopg2 using the URL.
    conn = psycopg2.connect(DATABASE_URL)
    # Enable autocommit so DDL like CREATE TABLE works without manual commit.
    conn.autocommit = True
    return conn