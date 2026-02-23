-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Main chunks table
CREATE TABLE IF NOT EXISTS rag_chunks (
    id            BIGSERIAL PRIMARY KEY,
    doc_id        TEXT        NOT NULL,
    doc_version   TEXT        NOT NULL,
    chunk_id      TEXT        NOT NULL,
    chunk_index   INT         NOT NULL,
    content_type  TEXT        NOT NULL,
    text          TEXT        NOT NULL,
    embedding     VECTOR(384) NOT NULL,
    metadata      JSONB       NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT rag_chunks_unique UNIQUE (doc_id, doc_version, chunk_id)
);