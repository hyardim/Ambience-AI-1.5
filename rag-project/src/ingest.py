# src/ingest.py

# Import os for file walking.
import os

# Import typing.
from typing import List, Dict

# Import tqdm for progress bars.
from tqdm import tqdm

# Import our components.
from .config import RAG_DATA_DIR
from .extract import extract_pdf_pages
from .clean import clean_lines_iterative, fix_stuttering_headers
from .chunk import chunk_pages
from .embed import load_embedder, embed_chunks, get_vector_dim
from .metadata import sha256_file, parse_specialty_publisher_from_path, guess_title_from_filename, extract_published_date_from_frontmatter
from .db import init_db, upsert_document, delete_chunks_for_doc, insert_chunks

def find_pdfs(root_dir: str) -> List[str]:
    """
    Recursively find all PDFs under root_dir.
    """
    pdfs = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".pdf"):
                pdfs.append(os.path.join(dirpath, fn))
    return sorted(pdfs)

def ingest_all() -> None:
    """
    Full ingestion:
    - scan PDFs
    - extract pages
    - clean
    - chunk (with page attribution)
    - embed
    - upsert document metadata
    - delete old chunks
    - insert new chunks into pgvector
    """
    # Load embedding model once.
    model = load_embedder()

    # Determine embedding dimensionality once.
    dim = get_vector_dim(model)

    # Initialize DB schema + HNSW index.
    init_db(vector_dim=dim)

    # Find all PDFs.
    pdf_paths = find_pdfs(RAG_DATA_DIR)

    print(f"Found {len(pdf_paths)} PDFs under {RAG_DATA_DIR}")

    # Loop each PDF.
    for pdf_path in tqdm(pdf_paths, desc="Ingesting PDFs"):
        # Compute file hash (stable doc ID).
        file_hash = sha256_file(pdf_path)

        # Extract metadata from folder structure.
        specialty, publisher = parse_specialty_publisher_from_path(pdf_path, RAG_DATA_DIR)

        # Basic filename + title.
        filename = os.path.basename(pdf_path)
        title = guess_title_from_filename(filename)

        # Extract pages (raw).
        pages = extract_pdf_pages(pdf_path)

        # Combine first ~2 pages as “front matter” for date detection.
        front_text = " ".join([p["text"] for p in pages[:2]])
        published_date_iso = extract_published_date_from_frontmatter(front_text)

        # Build document record.
        doc = {
            "doc_id": file_hash,
            "filename": filename,
            "source_path": pdf_path,
            "specialty": specialty,
            "publisher": publisher,
            "title": title,
            "published_date": published_date_iso,  # ISO string (db will cast)
            "file_sha256": file_hash,
        }

        # Upsert document metadata row.
        upsert_document(doc)

        # Delete existing chunks for this doc (clean re-ingestion).
        delete_chunks_for_doc(file_hash)

        # Clean each page separately (keeps citations simple).
        cleaned_page_texts = []
        for p in pages:
            # Clean the page text.
            clean = clean_lines_iterative(p["text"])
            # Fix header stutter if present.
            clean = fix_stuttering_headers(clean)
            cleaned_page_texts.append(clean)

        # Chunk with page tracking.
        chunks = chunk_pages(pages, cleaned_page_texts)

        # Attach doc_id to each chunk now.
        for c in chunks:
            c["doc_id"] = file_hash

        # Embed + hash chunks.
        chunks = embed_chunks(model, chunks, batch_size=64)

        # Insert into DB.
        insert_chunks(chunks)

    print("✅ Ingestion complete.")

if __name__ == "__main__":
    ingest_all()
