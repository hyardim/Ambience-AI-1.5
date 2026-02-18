-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: one row per source PDF
CREATE TABLE IF NOT EXISTS documents (
    id              SERIAL PRIMARY KEY,
    filename        TEXT NOT NULL,
    specialty       TEXT NOT NULL,
    publisher       TEXT NOT NULL,
    file_path       TEXT NOT NULL UNIQUE,
    total_pages     INTEGER,
    total_chunks    INTEGER DEFAULT 0,
    ingested_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- Chunks table: one row per text chunk
CREATE TABLE IF NOT EXISTS chunks (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(384),
    page_number     INTEGER,
    section_title   TEXT,
    chunk_type      TEXT,
    token_count     INTEGER,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- HNSW index for fast vector similarity search
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Index for fast document lookups
CREATE INDEX IF NOT EXISTS chunks_document_id_idx
    ON chunks (document_id);

-- GIN index for metadata queries
CREATE INDEX IF NOT EXISTS chunks_metadata_idx
    ON chunks USING GIN (metadata);