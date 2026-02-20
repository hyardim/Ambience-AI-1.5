# src/chunk.py

# Import typing.
from typing import List, Dict, Tuple

# Import LangChain splitter (simple, reliable).
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Import config chunk sizes.
from src.config import CHUNK_SIZE, CHUNK_OVERLAP

def chunk_pages(pages: List[Dict], cleaned_page_texts: List[str]) -> List[Dict]:
    """
    Chunk text with page tracking so we can cite page ranges.

    pages: [{"page": 1, "text": "..."}, ...]
    cleaned_page_texts: ["cleaned page 1 text", "cleaned page 2 text", ...]

    Returns list of chunk dicts (without embeddings yet).
    """
    # Create the text splitter.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # We'll store all chunks here.
    chunks = []

    # chunk_index increments across the whole document.
    chunk_index = 0

    # We chunk *per page* to keep simple page attribution.
    # (You can later upgrade to multi-page chunking with exact spans.)
    for i, page in enumerate(pages):
        # Get the cleaned text for this page.
        page_text = cleaned_page_texts[i]

        # Split into chunks.
        page_chunks = splitter.split_text(page_text)

        # Turn each into a chunk record.
        for c in page_chunks:
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "page_start": page["page"],
                    "page_end": page["page"],
                    "section_path": None,  # placeholder for future “section heading” logic
                    "text": c,
                }
            )
            chunk_index += 1

    return chunks
