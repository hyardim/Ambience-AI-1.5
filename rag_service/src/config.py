# src/config.py

# Import os so we can read environment variables.
import os

# Import dotenv so we can load .env automatically.
from dotenv import load_dotenv

# Load environment variables from .env into os.environ.
load_dotenv()

# Database URL for Postgres + pgvector (from .env).
# Example:
#   postgresql://admin:team20_password@localhost:5432/ambience_knowledge
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:team20_password@localhost:5432/ambience_knowledge",
)

# Ollama connection (reachable from inside Docker via host.docker.internal)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "thewindmom/llama3-med42-8b")
# Default max tokens for completions (can be overridden per request)
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "512"))

# Root directory containing PDFs arranged like:
#   rag_data/<specialty>/<publisher>/*.pdf
RAG_DATA_DIR = os.getenv("RAG_DATA_DIR", "rag_data")

# SentenceTransformers model name.
MODEL_NAME = os.getenv("MODEL_NAME", "all-MiniLM-L6-v2")

# Chunking parameters.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "450"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# HNSW index parameters for pgvector.
HNSW_M = int(os.getenv("HNSW_M", "16"))
HNSW_EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "64"))