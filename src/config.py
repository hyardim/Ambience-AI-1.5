# src/config.py

# We import "os" to read environment variables like DATABASE_URL.
import os

# We import "dotenv" so we can load variables from a .env file automatically.
from dotenv import load_dotenv

# Load variables from .env into the process environment.
load_dotenv()

# Read the database connection string from the environment.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ragdb")

# The folder where your PDFs live (rag_data/...).
RAG_DATA_DIR = os.getenv("RAG_DATA_DIR", "rag_data")

# The embedding model to use (SentenceTransformers model name).
MODEL_NAME = os.getenv("MODEL_NAME", "all-MiniLM-L6-v2")

# Chunking settings.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "450"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# HNSW index parameters (pgvector).
HNSW_M = int(os.getenv("HNSW_M", "16"))
HNSW_EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "64"))
