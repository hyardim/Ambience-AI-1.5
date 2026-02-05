import json
import sys
import os
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------
# DB Connection Import
# ---------------------------------------------------------
try:
    from app.db import get_conn
except ImportError:
    print("Warning: Could not import get_conn from app.db")
    get_conn = None

# ---------------------------------------------------------
# 1. INIT DB (Creates Tables)
# ---------------------------------------------------------
def init_db(vector_dim: int = 768):
    """
    Creates the 'documents' and 'chunks' tables if they don't exist.
    Enables the pgvector extension.
    """
    conn = get_conn()
    if not conn:
        print("❌ DB Connection failed in init_db.")
        return

    try:
        with conn.cursor() as cur:
            # Enable vector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Create Documents Table (Stores file info)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT,
                source_path TEXT,
                specialty TEXT,
                publisher TEXT,
                title TEXT,
                published_date TIMESTAMP,
                file_sha256 TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Create Chunks Table (Stores text + vectors)
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id SERIAL PRIMARY KEY,
                doc_id TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
                text TEXT,
                page_num INTEGER,
                embedding vector({vector_dim}),
                metadata JSONB
            );
            """)
        
        conn.commit()
        print("✅ Database tables initialized.")
    except Exception as e:
        print(f"Error initializing DB: {e}")
        conn.rollback()
    finally:
        conn.close()

# ---------------------------------------------------------
# 2. UPSERT DOCUMENT (Saves Metadata)
# ---------------------------------------------------------
def upsert_document(doc: Dict[str, Any]):
    """
    Inserts a document record. If it exists, updates the details.
    """
    conn = get_conn()
    if not conn: return

    sql = """
    INSERT INTO documents (doc_id, filename, source_path, specialty, publisher, title, published_date, file_sha256)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (doc_id) DO UPDATE SET
        filename = EXCLUDED.filename,
        source_path = EXCLUDED.source_path,
        specialty = EXCLUDED.specialty,
        publisher = EXCLUDED.publisher,
        title = EXCLUDED.title,
        published_date = EXCLUDED.published_date,
        file_sha256 = EXCLUDED.file_sha256;
    """
    params = (
        doc.get("doc_id"), doc.get("filename"), doc.get("source_path"),
        doc.get("specialty"), doc.get("publisher"), doc.get("title"),
        doc.get("published_date"), doc.get("file_sha256")
    )

    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception as e:
        print(f"Error upserting document: {e}")
        conn.rollback()
    finally:
        conn.close()

# ---------------------------------------------------------
# 3. DELETE CHUNKS (Cleans up old data)
# ---------------------------------------------------------
def delete_chunks_for_doc(doc_id: str):
    """
    Removes old chunks for a document before re-ingesting.
    """
    conn = get_conn()
    if not conn: return

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting chunks: {e}")
        conn.rollback()
    finally:
        conn.close()

# ---------------------------------------------------------
# 4. INSERT CHUNKS (Saves Vectors)
# ---------------------------------------------------------
def insert_chunks(chunks: List[Dict[str, Any]]):
    """
    Bulk inserts text chunks and their vector embeddings.
    """
    if not chunks: return

    conn = get_conn()
    if not conn: return

    sql = """
    INSERT INTO chunks (doc_id, text, page_num, embedding, metadata)
    VALUES (%s, %s, %s, %s, %s)
    """

    try:
        with conn.cursor() as cur:
            data_to_insert = []
            for c in chunks:
                # Handle optional fields safely
                page = c.get("page_num", 1)
                meta = c.get("metadata", {})
                
                data_to_insert.append((
                    c["doc_id"],
                    c["text"],
                    page,
                    c["embedding"],  # This is the list of floats
                    json.dumps(meta)
                ))
            
            cur.executemany(sql, data_to_insert)
        conn.commit()
    except Exception as e:
        print(f"Error inserting chunks: {e}")
        conn.rollback()
    finally:
        conn.close()

# ---------------------------------------------------------
# 5. SEARCH (The "Read" Function)
# ---------------------------------------------------------
def search_similar_chunks(query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Performs a cosine similarity search in Postgres using pgvector.
    """
    conn = get_conn()
    if not conn:
        print("Database connection not available.")
        return []

    results = []
    try:
        with conn.cursor() as cur:
            sql = """
            SELECT 
                c.text,
                c.doc_id,
                d.filename,
                d.title,
                1 - (c.embedding <=> %s::vector) as similarity
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s;
            """
            cur.execute(sql, (query_embedding, query_embedding, limit))
            rows = cur.fetchall()
            
            for row in rows:
                results.append({
                    "text": row[0],
                    "doc_id": row[1],
                    "filename": row[2],
                    "title": row[3],
                    "score": float(row[4])
                })
                
    except Exception as e:
        print(f"Database Search Error: {e}")
    finally:
        if conn:
            conn.close()
    return results