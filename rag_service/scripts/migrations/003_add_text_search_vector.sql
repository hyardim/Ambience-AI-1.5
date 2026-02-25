-- Migration 003: Add text_search_vector column to rag_chunks
-- Required for keyword search stage of the retrieval pipeline.
-- Generated column stays in sync with text automatically.
-- Safe to run multiple times (IF NOT EXISTS).

ALTER TABLE rag_chunks
    ADD COLUMN IF NOT EXISTS text_search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;

CREATE INDEX IF NOT EXISTS idx_rag_chunks_text_search
    ON rag_chunks
    USING GIN (text_search_vector);