from typing import Any

import psycopg2
import psycopg2.extras

from src.config import DATABASE_URL, HNSW_EF_CONSTRUCTION, HNSW_M


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
    conn = get_conn()
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
                                WHERE  c.relname = 'idx_rag_chunks_embedding_hnsw'
                            ) THEN
                                CREATE INDEX idx_rag_chunks_embedding_hnsw
                                ON rag_chunks
                                USING hnsw (embedding vector_cosine_ops)
                                WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION});
                            END IF;
                        END $$;
                        """
                )

    conn.close()


def delete_chunks_for_doc(doc_id: str) -> None:
    """
    Deletes all chunks for a given document (used for clean re-ingestion).
    """
    conn = get_conn()
    with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_chunks WHERE doc_id = %s;", (doc_id,))
    conn.close()


def insert_chunks(chunks: list[dict[str, Any]]) -> None:
    """
    Bulk-inserts chunk rows.
    """
    if not chunks:
        return

    conn = get_conn()
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO rag_chunks (
                doc_id,
                doc_version,
                chunk_id,
                chunk_index,
                content_type,
                text,
                embedding,
                metadata
            )
            VALUES %s
            ON CONFLICT (doc_id, doc_version, chunk_id) DO UPDATE SET
                chunk_index = EXCLUDED.chunk_index,
                content_type = EXCLUDED.content_type,
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            [
                (
                    c["doc_id"],
                    c["doc_version"],
                    c["chunk_id"],
                    c["chunk_index"],
                    c.get("content_type", "text/plain"),
                    c["text"],
                    c["embedding"],
                    c.get("metadata", {}),
                )
                for c in chunks
            ],
            page_size=500,
        )
    conn.close()


def search_similar_chunks(
    query_embedding: list[float], limit: int = 5
) -> list[dict[str, Any]]:
    """Performs a vector similarity search (Cosine Distance) to find relevant chunks."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    id,
                    doc_id,
                    doc_version,
                    chunk_id,
                    chunk_index,
                    content_type,
                    text,
                    metadata,
                    (1 - (embedding <=> %s::vector)) AS score
                FROM rag_chunks
                ORDER BY embedding <=> %s::vector ASC
                LIMIT %s;
                """,
                (query_embedding, query_embedding, limit),
            )
            results = cur.fetchall()

        return [
            {
                "id": row[0],
                "doc_id": row[1],
                "doc_version": row[2],
                "chunk_id": row[3],
                "chunk_index": row[4],
                "content_type": row[5],
                "text": row[6],
                "metadata": row[7] or {},
                "score": float(row[8]),
                "page_start": (row[7] or {}).get("page_start"),
                "page_end": (row[7] or {}).get("page_end"),
                "section_path": (row[7] or {}).get("section_path"),
            }
            for row in results
        ]
    finally:
        conn.close()
