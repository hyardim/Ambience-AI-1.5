#!/bin/bash

# --- 1. RAG SERVICE MIGRATION ---
echo "Migrating RAG Service..."
mkdir -p rag_service/src/ingestion
mkdir -p rag_service/src/retrieval
mkdir -p rag_service/src/llm

# Move Data Pipeline files
mv rag_service/src/extract.py rag_service/src/ingestion/ 2>/dev/null
mv rag_service/src/clean.py rag_service/src/ingestion/ 2>/dev/null
mv rag_service/src/chunk.py rag_service/src/ingestion/ 2>/dev/null
mv rag_service/src/embed.py rag_service/src/ingestion/ 2>/dev/null
mv rag_service/src/ingest.py rag_service/src/ingestion/ 2>/dev/null
mv rag_service/src/metadata.py rag_service/src/ingestion/ 2>/dev/null

# Move DB logic (renaming db.py to vector_store.py)
mv rag_service/src/db.py rag_service/src/retrieval/vector_store.py 2>/dev/null

# Move Config
mv rag_service/src/config.py rag_service/src/config.py 2>/dev/null

# Move Dockerfile and requirements to root
mv rag_service/src/Dockerfile rag_service/Dockerfile 2>/dev/null
mv rag_service/src/requirements.txt rag_service/requirements.txt 2>/dev/null

# Create Init files
touch rag_service/src/ingestion/__init__.py
touch rag_service/src/retrieval/__init__.py
touch rag_service/src/llm/__init__.py

# Create LLM placeholders
touch rag_service/src/llm/client.py
touch rag_service/src/llm/prompts.py


# --- 2. BACKEND MIGRATION ---
echo "Migrating Backend..."
mkdir -p backend/app/services
mkdir -p backend/app/repositories
mkdir -p backend/app/schemas
mkdir -p backend/app/api/v1/endpoints
mkdir -p backend/alembic/versions

# Move Dockerfile
mv backend/app/Dockerfile backend/Dockerfile 2>/dev/null

# Create missing backend files
touch backend/app/services/__init__.py
touch backend/app/repositories/__init__.py
touch backend/app/schemas/__init__.py
touch backend/alembic.ini
touch backend/app/api/deps.py
mkdir -p backend/app/utils
touch backend/app/utils/logging.py

# --- 3. ROOT CLEANUP ---
echo "Setting up Root..."
mkdir -p scripts
mkdir -p deploy/nginx
touch .pre-commit-config.yaml
touch pytest.ini

echo "MIGRATION COMPLETE!"
