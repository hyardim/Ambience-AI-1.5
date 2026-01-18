# We import typing helpers for clearer function signatures.
from typing import Any, Dict, List, Optional, Tuple

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


def init_db(vector_dim: int) -> None:
    """
    Creates pgvector extension, tables, and indexes if they don't exist.
    Uses HNSW for the embedding index.
    """
    # Open a DB connection.
    conn = get_conn()

    # Create a cursor to execute SQL commands.
    with conn.cursor() as cur:
        # Ensure pgvector extension exists.
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Create documents table to store document-level metadata.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
              doc_id TEXT PRIMARY KEY,
              filename TEXT NOT NULL,
              source_path TEXT NOT NULL,
              specialty TEXT NOT NULL,
              publisher TEXT NOT NULL,
              title TEXT,
              published_date DATE,
              file_sha256 TEXT NOT NULL,
              ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # Create chunks table to store text chunks + embeddings + chunk-level metadata.
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunks (
              chunk_id BIGSERIAL PRIMARY KEY,
              doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
              chunk_index INT NOT NULL,
              page_start INT NOT NULL,
              page_end INT NOT NULL,
              section_path TEXT,
              text TEXT NOT NULL,
              text_hash TEXT NOT NULL,
              embedding VECTOR({vector_dim}) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # Helpful index to quickly filter chunks by document.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")

        # Helpful index to quickly deduplicate by text_hash.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash);")

        # Create HNSW vector index for fast approximate nearest neighbor search.
        # We use cosine distance ops because it’s common for sentence embeddings.
        # If you prefer L2, swap vector_cosine_ops -> vector_l2_ops.
        cur.execute(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM   pg_class c
                JOIN   pg_namespace n ON n.oid = c.relnamespace
                WHERE  c.relname = 'idx_chunks_embedding_hnsw'
              ) THEN
                CREATE INDEX idx_chunks_embedding_hnsw
                ON chunks
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION});
              END IF;
            END $$;
            """
        )

    # Close the connection.
    conn.close()
