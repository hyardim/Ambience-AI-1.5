-- HNSW vector index for cosine similarity search
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
    ON rag_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Btree indexes for metadata filtering
CREATE INDEX IF NOT EXISTS rag_chunks_doc_id_idx
    ON rag_chunks (doc_id);

CREATE INDEX IF NOT EXISTS rag_chunks_doc_version_idx
    ON rag_chunks (doc_version);

CREATE INDEX IF NOT EXISTS rag_chunks_content_type_idx
    ON rag_chunks (content_type);

-- GIN index for jsonb metadata filtering
CREATE INDEX IF NOT EXISTS rag_chunks_metadata_idx
    ON rag_chunks USING GIN (metadata);