import psycopg2
from psycopg2.extensions import connection as PsycopgConnection

from ..config import db_config, vector_config
from ..utils.db import db


def get_conn() -> PsycopgConnection:
    """
    Creates and returns a Postgres connection using the configured database URL.
    """
    # Connect to Postgres with psycopg2 using the configured URL.
    conn = psycopg2.connect(db_config.database_url)
    # Enable autocommit so DDL like CREATE TABLE works without manual commit.
    conn.autocommit = True
    return conn


def init_db(vector_dim: int) -> None:
    """
    Creates pgvector extension, tables, and indexes if they don't exist.
    Uses HNSW for the embedding index.
    """
    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id            BIGSERIAL PRIMARY KEY,
                    doc_id        TEXT        NOT NULL,
                    doc_version   TEXT        NOT NULL,
                    chunk_id      TEXT        NOT NULL,
                    chunk_index   INT         NOT NULL,
                    content_type  TEXT        NOT NULL,
                    text          TEXT        NOT NULL,
                    embedding     VECTOR({vector_dim}) NOT NULL,
                    metadata      JSONB       NOT NULL,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    CONSTRAINT rag_chunks_unique UNIQUE (doc_id, doc_version, chunk_id)
                );
                """
            )
            cur.execute(
                f"""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                    FROM   pg_class c
                    JOIN   pg_namespace n ON n.oid = c.relnamespace
                    WHERE  c.relname IN (
                      'idx_rag_chunks_embedding_hnsw',
                      'rag_chunks_embedding_idx'
                    )
                  ) THEN
                    CREATE INDEX rag_chunks_embedding_idx
                    ON rag_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (
                      m = {vector_config.hnsw_m},
                      ef_construction = {vector_config.hnsw_ef_construction}
                    );
                  END IF;
                END $$;
                """
            )
    finally:
        conn.close()


def get_source_path_for_doc(doc_id: str) -> str | None:
    """Return the source_path for a given doc_id, if present in metadata."""
    with db.raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT metadata->>'source_path'
            FROM rag_chunks
            WHERE doc_id = %s
            LIMIT 1;
            """,
            (doc_id,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
