from __future__ import annotations

from pathlib import Path

from src.ingestion import (
    chunk,
    clean,
    embed,
    extract,
    metadata,
    pipeline,
    section_detect,
    store,
    table_detect,
)


def _raw_doc_with_noise() -> dict:
    return {
        "source_path": "/tmp/doc.pdf",
        "num_pages": 1,
        "needs_ocr": False,
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": 0,
                        "text": (
                            "NICE HEADER\n"
                            "This is \ufb01rst para with hyphen-\nation and \ufb02ow.\n"
                            "Page 1"
                        ),
                        "bbox": [0, 10, 500, 40],
                        "font_size": 11.0,
                        "font_name": "Helvetica",
                        "is_bold": False,
                    },
                    {
                        "block_id": 1,
                        "text": "1. Introduction",
                        "bbox": [0, 120, 500, 140],
                        "font_size": 18.0,
                        "font_name": "Helvetica-Bold",
                        "is_bold": True,
                    },
                    {
                        "block_id": 2,
                        "text": "1.1 Background",
                        "bbox": [0, 170, 500, 190],
                        "font_size": 16.0,
                        "font_name": "Helvetica-Bold",
                        "is_bold": True,
                    },
                    {
                        "block_id": 3,
                        "text": "Patient outcomes improve with early treatment.",
                        "bbox": [0, 220, 500, 260],
                        "font_size": 11.0,
                        "font_name": "Helvetica",
                        "is_bold": False,
                    },
                ],
            }
        ],
    }


def test_extract_to_clean_pipeline(monkeypatch):
    class _FakePage:
        rect = type("Rect", (), {"width": 595.0})()

        def get_text(self, mode):
            return {
                "blocks": [
                    {
                        "type": 0,
                        "bbox": [0, 260, 300, 300],
                        "lines": [
                            {
                                "spans": [
                                    {
                                        "text": (
                                            "This \ufb01nding has hyphen-\nation"
                                            " and \ufb02ow"
                                        ),
                                        "size": 11,
                                        "font": "Helvetica",
                                        "flags": 0,
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }

    class _FakeDoc:
        page_count = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            yield _FakePage()

    monkeypatch.setattr(extract, "_open_pdf", lambda _: _FakeDoc())

    raw = extract.extract_raw_document("/tmp/source.pdf")
    cleaned = clean.clean_document(raw)
    text = cleaned["pages"][0]["blocks"][0]["text"]

    assert "fi" in text
    assert "hyphenation" in text
    assert "ﬂ" not in text


def test_clean_to_section_detect_pipeline():
    cleaned = clean.clean_document(_raw_doc_with_noise())
    sectioned = section_detect.add_section_metadata(cleaned)

    paths = [
        b["section_path"]
        for b in sectioned["pages"][0]["blocks"]
        if not b.get("is_heading")
    ]
    assert any(path and "Background" in path[-1] for path in paths)


def test_section_to_table_detect_pipeline(monkeypatch):
    sectioned = section_detect.add_section_metadata(
        clean.clean_document(_raw_doc_with_noise())
    )

    monkeypatch.setattr(
        table_detect,
        "detect_tables_with_pymupdf",
        lambda pdf_path, page_num: [
            {
                "cells": [["Drug", "Dose"], ["Pred", "20mg"]],
                "bbox": [0, 215, 500, 265],
                "page_number": page_num,
            }
        ],
    )

    with_tables = table_detect.detect_and_convert_tables(
        sectioned, pdf_path="/tmp/a.pdf"
    )
    table_blocks = [
        b
        for page in with_tables["pages"]
        for b in page["blocks"]
        if b.get("content_type") == "table"
    ]
    assert table_blocks
    assert "| Drug | Dose |" in table_blocks[0]["text"]


def test_metadata_extraction_from_sections(monkeypatch):
    sectioned = section_detect.add_section_metadata(
        clean.clean_document(_raw_doc_with_noise())
    )
    table_aware = table_detect.detect_and_convert_tables(
        sectioned, pdf_path="/tmp/x.pdf"
    )

    monkeypatch.setattr(metadata, "validate_source_info", lambda _: None)
    monkeypatch.setattr(
        metadata,
        "extract_pdf_metadata",
        lambda _: {
            "title": "MS Guideline",
            "creationDate": "2024-01-01",
            "modDate": "2024-02-01",
            "uid": "u1",
        },
    )

    enriched = metadata.attach_metadata(
        table_aware,
        {
            "source_name": "NICE",
            "source_path": "/tmp/raw/neurology/NICE/guide.pdf",
            "doc_type": "guideline",
            "specialty": "neurology",
            "publish_date": "2024-01-01",
        },
    )

    assert enriched["doc_meta"]["title"]
    assert enriched["doc_meta"]["source_name"] == "NICE"
    assert all("block_uid" in b for p in enriched["pages"] for b in p["blocks"])


def test_full_chunking_pipeline(monkeypatch):
    sectioned = section_detect.add_section_metadata(
        clean.clean_document(_raw_doc_with_noise())
    )
    table_aware = table_detect.detect_and_convert_tables(
        sectioned, pdf_path="/tmp/x.pdf"
    )

    monkeypatch.setattr(metadata, "validate_source_info", lambda _: None)
    monkeypatch.setattr(
        metadata,
        "extract_pdf_metadata",
        lambda _: {
            "title": "Chunk Test",
            "creationDate": "",
            "modDate": "",
            "uid": "u2",
        },
    )
    monkeypatch.setattr(
        chunk,
        "split_into_sentences",
        lambda text: [s.strip() for s in text.split(".") if s.strip()],
    )

    enriched = metadata.attach_metadata(
        table_aware,
        {
            "source_name": "NICE",
            "source_path": "/tmp/raw/neurology/NICE/guide.pdf",
            "doc_type": "guideline",
            "specialty": "neurology",
        },
    )
    chunked = chunk.chunk_document(
        enriched, chunking_config={"target_chunk_size": 40, "overlap_tokens": 5}
    )

    assert chunked["chunks"]
    assert all(c["section_path"] for c in chunked["chunks"])
    assert all(
        c["token_count"] <= 40 for c in chunked["chunks"] if c["content_type"] == "text"
    )


def test_embed_chunks_batching(monkeypatch):
    calls = {"sizes": []}

    class _FakeVec:
        def __init__(self, vals):
            self._vals = vals

        def tolist(self):
            return self._vals

    class _FakeModel:
        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            calls["sizes"].append(len(texts))
            return [_FakeVec([0.1, 0.2, 0.3]) for _ in texts]

    monkeypatch.setattr(embed, "_load_model", lambda model_name=None: _FakeModel())

    chunked_doc = {
        "doc_meta": {"doc_id": "d1", "doc_version": "v1"},
        "chunks": [
            {"chunk_id": f"c{i}", "text": f"chunk {i}", "content_type": "text"}
            for i in range(5)
        ],
    }

    embedded = embed.embed_chunks(
        chunked_doc, embedding_config={"batch_size": 2, "dimensions": 3}
    )
    assert calls["sizes"] == [2, 2, 1]
    assert all(c["embedding_status"] == "success" for c in embedded["chunks"])
    assert all(len(c["embedding"]) == 3 for c in embedded["chunks"])


def test_store_chunks_to_vector_db(monkeypatch):
    actions = iter(["inserted", "updated"])

    class _FakeCursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            return None

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(store.psycopg2, "connect", lambda db_url: _FakeConn())
    monkeypatch.setattr(store, "register_vector", lambda conn: None)
    monkeypatch.setattr(
        store.psycopg2.extras, "register_default_jsonb", lambda conn: None
    )
    monkeypatch.setattr(
        store, "_upsert_chunk", lambda conn, chunk, doc_id, doc_version: next(actions)
    )

    embedded_doc = {
        "doc_meta": {"doc_id": "d1", "doc_version": "v1"},
        "chunks": [
            {
                "chunk_id": "c1",
                "embedding_status": "success",
                "embedding": [0.1],
                "text": "A",
                "chunk_index": 0,
                "content_type": "text",
                "citation": {},
            },
            {
                "chunk_id": "c2",
                "embedding_status": "success",
                "embedding": [0.2],
                "text": "B",
                "chunk_index": 1,
                "content_type": "text",
                "citation": {},
            },
        ],
    }

    report = store.store_chunks(embedded_doc, db_url="postgres://test")
    assert report["inserted"] == 1
    assert report["updated"] == 1
    assert report["failed"] == 0


def test_full_ingestion_extract_to_store(monkeypatch, tmp_path):
    pdf_path = tmp_path / "guide.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    monkeypatch.setattr(
        pipeline, "extract_raw_document", lambda _: _raw_doc_with_noise()
    )
    monkeypatch.setattr(metadata, "validate_source_info", lambda _: None)
    monkeypatch.setattr(
        metadata,
        "extract_pdf_metadata",
        lambda _: {
            "title": "Pipeline E2E",
            "creationDate": "",
            "modDate": "",
            "uid": "u3",
        },
    )
    monkeypatch.setattr(
        chunk,
        "split_into_sentences",
        lambda text: [s.strip() for s in text.split(".") if s.strip()],
    )
    monkeypatch.setattr(
        embed,
        "_load_model",
        lambda model_name=None: type(
            "M",
            (),
            {
                "encode": lambda self, texts, **k: [
                    type("V", (), {"tolist": lambda self2: [0.1, 0.2, 0.3]})()
                    for _ in texts
                ]
            },
        )(),
    )
    monkeypatch.setattr(
        pipeline,
        "store_chunks",
        lambda embedded_doc, db_url: {
            "inserted": len(embedded_doc["chunks"]),
            "updated": 0,
            "skipped": 0,
            "failed": 0,
        },
    )

    report = pipeline.run_pipeline(
        pdf_path=Path(pdf_path),
        source_info={
            "source_name": "NICE",
            "doc_type": "guideline",
            "specialty": "neurology",
        },
        db_url="postgres://unused",
        dry_run=False,
        write_debug_artifacts=False,
    )

    assert report["chunks"] > 0
    assert report["embeddings_succeeded"] == report["chunks"]
    assert report["db"]["inserted"] == report["chunks"]
