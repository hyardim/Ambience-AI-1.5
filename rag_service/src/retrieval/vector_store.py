from pathlib import Path

import psycopg2
from psycopg2.extensions import connection as PsycopgConnection

from ..config import db_config, path_config, vector_config
from ..utils.db import db


def _remap_source_path_to_data_root(source_path: str) -> Path | None:
    """Map host/container absolute paths containing ``data/raw`` to local data root."""
    normalized = source_path.replace("\\", "/")
    marker = "/data/raw/"
    if marker not in normalized:
        return None
    tail = normalized.split(marker, 1)[1]
    if not tail:
        return None
    return path_config.data_raw / tail


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
    """Return a resolvable source_path for a given doc_id, if available."""
    with db.raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT metadata->>'source_path' AS source_path,
                   MAX(updated_at) AS last_seen
            FROM rag_chunks
            WHERE doc_id = %s
              AND COALESCE(metadata->>'source_path', '') <> ''
            GROUP BY metadata->>'source_path'
            ORDER BY MAX(updated_at) DESC;
            """,
            (doc_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return None

        for row in rows:
            source_path = row[0]
            if not source_path:
                continue
            candidates: list[Path] = []
            original = Path(source_path)
            candidates.append(original)
            if not original.is_absolute():
                candidates.append((path_config.root / original).resolve())
            remapped = _remap_source_path_to_data_root(source_path)
            if remapped is not None:
                candidates.append(remapped.resolve())

            seen: set[str] = set()
            for candidate in candidates:
                key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                if candidate.exists():
                    return str(candidate.resolve())

        # Fall back to the newest stored source path even if the file is gone.
        # The caller endpoint will surface a clear 404 for missing files.
        fallback = rows[0][0]
        return str(fallback) if fallback else None
