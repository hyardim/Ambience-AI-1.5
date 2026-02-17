import sys
import os

# 1. Add the current folder to the Python path so we can find 'src'
sys.path.append(os.getcwd())

try:
    from src.db import get_conn
except ImportError:
    print("❌ Error: Could not import 'src.db'. Make sure you are running this from the project root.")
    sys.exit(1)

def init_db():
    print("--- STARTING DATABASE SETUP ---")
    
    # 2. Get connection
    conn = get_conn()
    if conn is None:
        print("❌ Failed to connect to the database. Is Docker running?")
        return

    try:
        with conn.cursor() as cur:
            print("⚙️  Creating tables...")
            
            # 3. Enable the Vector Extension (Crucial for AI)
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # 4. Create 'documents' table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            
            # 5. Create 'chunks' table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id SERIAL PRIMARY KEY,
                doc_id INTEGER REFERENCES documents(doc_id),
                text TEXT NOT NULL,
                embedding vector(768)
            );
            """)
            
            conn.commit()
            print("✅ Success! Tables 'documents' and 'chunks' are ready.")
            
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()