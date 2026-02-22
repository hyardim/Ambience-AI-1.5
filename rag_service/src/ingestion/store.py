from __future__ import annotations

import json
from typing import Any

import numpy as np
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from ..utils.db import db
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


def store_chunks(embedded_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Persist embedded chunks into Postgres + pgvector.

    Args:
        embedded_doc: EmbeddedDocument dict from embed.py

    Returns:
        Report dict with inserted, updated, skipped, failed counts

    Processing steps:
        1. Filter out failed chunks (embedding_status != "success")
        2. Connect to Postgres via db.get_raw_connection()
        3. For each chunk: determine upsert case and execute
        4. Return report
    """
    chunks = embedded_doc.get("chunks", [])
    doc_meta = embedded_doc.get("doc_meta", {})
    doc_id = doc_meta.get("doc_id", "")
    doc_version = doc_meta.get("doc_version", "")

    # Pre-filter failed chunks
    eligible = [c for c in chunks if c.get("embedding_status") == "success"]
    n_failed = len(chunks) - len(eligible)

    if not eligible:
        logger.info(f"No eligible chunks to store for doc_id={doc_id}")
        return {"inserted": 0, "updated": 0, "skipped": 0, "failed": n_failed}

    logger.info(f"Storing {len(eligible)} chunks for doc_id={doc_id}")

    report: dict[str, int] = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": n_failed,
    }

    conn = db.get_raw_connection()
    try:
        register_vector(conn)
        psycopg2.extras.register_default_jsonb(conn)
        for chunk in eligible:
            chunk_id = chunk.get("chunk_id", "")
            try:
                action = _upsert_chunk(conn, chunk, doc_id, doc_version)
                report[action] += 1
                logger.debug(f"Chunk {chunk_id}: {action}")
            except Exception as e:
                report["failed"] += 1
                logger.warning(f"Chunk {chunk_id} failed to write: {e}")
                conn.rollback()
    finally:
        conn.close()

    logger.info(
        f"Store report: inserted={report['inserted']} "
        f"updated={report['updated']} "
        f"skipped={report['skipped']} "
        f"failed={report['failed']}"
    )
    return report


def _upsert_chunk(
    conn: Any,
    chunk: dict[str, Any],
    doc_id: str,
    doc_version: str,
) -> str:
    """
    Upsert a single chunk. Returns "inserted" | "updated" | "skipped".
    Raises on DB error.
    """

    chunk_id = chunk["chunk_id"]
    text = chunk["text"]
    metadata = _build_metadata(chunk)
    metadata_str = _metadata_json(metadata)

    with conn.cursor() as cur:
        # Look up existing row
        cur.execute(
            """
            SELECT text, metadata
            FROM rag_chunks
            WHERE doc_id = %s AND doc_version = %s AND chunk_id = %s
            """,
            (doc_id, doc_version, chunk_id),
        )
        existing = cur.fetchone()

        if existing is None:
            # Case A — insert
            embedding = np.array(chunk["embedding"], dtype=np.float32)
            cur.execute(
                """
                INSERT INTO rag_chunks (
                    doc_id, doc_version, chunk_id, chunk_index,
                    content_type, text, embedding, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id,
                    doc_version,
                    chunk_id,
                    chunk["chunk_index"],
                    chunk["content_type"],
                    text,
                    embedding,
                    json.dumps(metadata),
                ),
            )
            conn.commit()
            return "inserted"

        existing_text, existing_metadata = existing
        existing_metadata_str = _metadata_json(existing_metadata)

        if existing_text != text:
            # Case B — text changed, update text + embedding + metadata
            embedding = np.array(chunk["embedding"], dtype=np.float32)
            cur.execute(
                """
                UPDATE rag_chunks
                SET text = %s,
                    embedding = %s,
                    metadata = %s,
                    updated_at = NOW()
                WHERE doc_id = %s AND doc_version = %s AND chunk_id = %s
                """,
                (
                    text,
                    embedding,
                    json.dumps(metadata),
                    doc_id,
                    doc_version,
                    chunk_id,
                ),
            )
            conn.commit()
            return "updated"

        if existing_metadata_str != metadata_str:
            # Case C — metadata only changed
            cur.execute(
                """
                UPDATE rag_chunks
                SET metadata = %s,
                    updated_at = NOW()
                WHERE doc_id = %s AND doc_version = %s AND chunk_id = %s
                """,
                (json.dumps(metadata), doc_id, doc_version, chunk_id),
            )
            conn.commit()
            return "updated"

        # Case D — identical, skip
        return "skipped"


def _build_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    """Extract and return the metadata jsonb payload from a chunk."""
    return {
        "source_name": chunk.get("citation", {}).get("source_name", ""),
        "title": chunk.get("citation", {}).get("title", ""),
        "section_path": chunk.get("section_path", []),
        "section_title": chunk.get("section_title", ""),
        "page_start": chunk.get("page_start", 0),
        "page_end": chunk.get("page_end", 0),
        "citation": chunk.get("citation", {}),
    }


def _metadata_json(metadata: dict[str, Any]) -> str:
    """Serialise metadata to sorted JSON string for comparison."""
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return json.dumps(metadata, sort_keys=True)
