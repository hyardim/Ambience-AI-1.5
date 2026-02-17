import sys
import os

# 1. Setup path to find 'app' and 'src'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("--- STARTING DATABASE CHECK ---")

try:
    # 2. Try to import your utility
    from app.db.utils import search_similar_chunks
    print("✅ Import successful: Found app.db.utils")

    # 3. Create a fake "query vector" (768 random numbers)
    mock_vector = [0.1] * 768

    print("Attempting to search database...")
    
    # 4. Run the function
    results = search_similar_chunks(mock_vector, limit=1)

    print("\n------------------------------------------------")
    print(f"CONNECTION SUCCESSFUL!")
    print(f"Query returned {len(results)} results.")
    print("------------------------------------------------")

except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    print("Make sure 'app/db/utils.py' exists.")
except Exception as e:
    print(f"CONNECTION ERROR: {e}")
    print("Check if Docker is running: 'docker compose up -d db_vector'")