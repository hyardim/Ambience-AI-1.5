import sys
import os
from typing import List, Dict, Any

# Add the 'src' directory to the system path so Python can find your friend's code
sys.path.append(os.path.join(os.path.dirname(__file__), "../../src"))

try:
    from src.db import get_conn
except ImportError:
    # This prevents the app from crashing if the DB isn't running yet
    print("Warning: Could not import get_conn from src.db")
    get_conn = None

def search_similar_chunks(query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Performs a cosine similarity search in Postgres using pgvector.
    """
    if not get_conn:
        print("Database connection not available.")
        return []

    conn = get_conn()
    results = []
    
    try:
        with conn.cursor() as cur:
            # SQL Query: Find text chunks that are mathematically closest to the question
            # The <=> operator is specific to pgvector for "cosine distance"
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