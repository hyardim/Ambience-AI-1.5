from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.pipeline import (
    PipelineError,
    _strip_embeddings,
    discover_pdfs,
    load_ingestion_config,
    load_sources,
    run_ingestion,
    run_pipeline,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

FAKE_SOURCE_INFO = {
    "source_name": "NICE",
    "author_org": "NICE",
    "specialty": "rheumatology",
    "doc_type": "guideline",
    "source_url": "https://www.nice.org.uk",
}

FAKE_DOC_META = {
    "doc_id": "abc123",
    "doc_version": "v1",
    "title": "RA Guidelines",
    "source_name": "NICE",
    "specialty": "rheumatology",
    "doc_type": "guideline",
    "source_path": "/data/raw/NICE/test.pdf",
    "ingestion_date": "2024-01-01",
    "author_org": "NICE",
    "source_url": "https://nice.org.uk",
    "creation_date": "",
    "publish_date": "",
    "last_updated_date": "",
}


def make_raw_doc() -> dict[str, Any]:
    return {
        "source_path": "/data/raw/NICE/test.pdf",
        "num_pages": 2,
        "needs_ocr": False,
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": 0,
                        "text": "Introduction",
                        "bbox": [0, 0, 100, 20],
                        "font_size": 14.0,
                        "font_name": "Arial",
                        "is_bold": True,
                    }
                ],
            }
        ],
    }


def make_embedded_doc() -> dict[str, Any]:
    return {
        "source_path": "/data/raw/NICE/test.pdf",
        "num_pages": 2,
        "needs_ocr": False,
        "doc_meta": FAKE_DOC_META,
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": 0,
                        "text": "Some text",
                        "bbox": [0, 0, 100, 20],
                        "font_size": 12.0,
                        "font_name": "Arial",
                        "is_bold": False,
                        "is_heading": False,
                        "content_type": "text",
                        "include_in_chunks": True,
                        "section_path": ["Introduction"],
                        "section_title": "Introduction",
                        "page_number": 1,
                        "block_uid": "uid001",
                    }
                ],
            }
        ],
        "chunks": [
            {
                "chunk_id": "chunk001",
                "chunk_index": 0,
                "content_type": "text",
                "text": "Some text",
                "section_path": ["Introduction"],
                "section_title": "Introduction",
                "page_start": 1,
                "page_end": 1,
                "block_uids": ["uid001"],
                "token_count": 10,
                "embedding": [0.1] * 384,
                "embedding_status": "success",
                "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
                "embedding_model_version": "main",
                "embedding_dimensions": 384,
                "embedding_error": None,
                "citation": {},
            }
        ],
    }


def make_db_report(
    inserted: int = 1,
    updated: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> dict[str, int]:
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }


PIPELINE_PATCHES = [
    "src.ingestion.pipeline.extract_raw_document",
    "src.ingestion.pipeline.clean_document",
    "src.ingestion.pipeline.add_section_metadata",
    "src.ingestion.pipeline.detect_and_convert_tables",
    "src.ingestion.pipeline.attach_metadata",
    "src.ingestion.pipeline.chunk_document",
    "src.ingestion.pipeline.embed_chunks",
    "src.ingestion.pipeline.store_chunks",
]


def make_all_patches(
    embedded_doc: dict[str, Any] | None = None,
) -> dict[str, MagicMock]:
    doc = embedded_doc or make_embedded_doc()
    raw = make_raw_doc()
    mocks = {}
    return_values = [raw, raw, raw, raw, doc, doc, doc, make_db_report()]
    for patch_path, rv in zip(PIPELINE_PATCHES, return_values, strict=True):
        m = MagicMock(return_value=rv)
        mocks[patch_path] = m
    return mocks


# -----------------------------------------------------------------------
# _strip_embeddings
# -----------------------------------------------------------------------


class TestStripEmbeddings:
    def test_strips_embedding_vectors(self) -> None:
        doc = make_embedded_doc()
        stripped = _strip_embeddings(doc)
        assert stripped["chunks"][0]["embedding"] == "<stripped>"

    def test_original_unchanged(self) -> None:
        doc = make_embedded_doc()
        _strip_embeddings(doc)
        assert doc["chunks"][0]["embedding"] == [0.1] * 384

    def test_no_chunks_returns_doc(self) -> None:
        doc = {"source_path": "x.pdf", "chunks": []}
        stripped = _strip_embeddings(doc)
        assert stripped["chunks"] == []


# -----------------------------------------------------------------------
# discover_pdfs
# -----------------------------------------------------------------------


class TestDiscoverPdfs:
    def test_single_pdf_file(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.touch()
        result = discover_pdfs(pdf)
        assert result == [pdf]

    def test_non_pdf_file_raises(self, tmp_path: Path) -> None:
        txt = tmp_path / "test.txt"
        txt.touch()
        with pytest.raises(ValueError, match="not a PDF"):
            discover_pdfs(txt)

    def test_folder_finds_pdfs_recursively(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.pdf").touch()
        (sub / "b.pdf").touch()
        result = discover_pdfs(tmp_path)
        assert len(result) == 2

    def test_folder_ignores_non_pdfs(self, tmp_path: Path) -> None:
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.txt").touch()
        result = discover_pdfs(tmp_path)
        assert len(result) == 1

    def test_max_files_limits_results(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"{i}.pdf").touch()
        result = discover_pdfs(tmp_path, max_files=2)
        assert len(result) == 2

    def test_since_filters_old_files(self, tmp_path: Path) -> None:
        import os

        old = tmp_path / "old.pdf"
        old.touch()
        os.utime(old, (0, 0))  # set mtime to epoch

        new = tmp_path / "new.pdf"
        new.touch()

        result = discover_pdfs(tmp_path, since=date(2000, 1, 1))
        assert new in result
        assert old not in result

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            discover_pdfs(tmp_path / "nonexistent")

    def test_empty_folder_returns_empty(self, tmp_path: Path) -> None:
        result = discover_pdfs(tmp_path)
        assert result == []


# -----------------------------------------------------------------------
# load_sources
# -----------------------------------------------------------------------


class TestLoadSources:
    def test_loads_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "sources.yaml"
        f.write_text("NICE:\n  source_name: NICE\n  specialty: rheumatology\n")
        result = load_sources(f)
        assert result["NICE"]["source_name"] == "NICE"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_sources(tmp_path / "missing.yaml")


# -----------------------------------------------------------------------
# load_ingestion_config
# -----------------------------------------------------------------------


class TestLoadIngestionConfig:
    def test_returns_empty_if_missing(self, tmp_path: Path) -> None:
        result = load_ingestion_config(tmp_path / "missing.yaml")
        assert result == {}

    def test_loads_yaml_if_present(self, tmp_path: Path) -> None:
        f = tmp_path / "ingestion.yaml"
        f.write_text("embedding:\n  dimensions: 384\n")
        result = load_ingestion_config(f)
        assert result["embedding"]["dimensions"] == 384


# -----------------------------------------------------------------------
# run_pipeline
# -----------------------------------------------------------------------


class TestRunPipeline:
    def _run(
        self,
        dry_run: bool = True,
        write_debug: bool = False,
        embedded_doc: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        doc = embedded_doc or make_embedded_doc()
        raw = make_raw_doc()
        with (
            patch("src.ingestion.pipeline.extract_raw_document", return_value=raw),
            patch("src.ingestion.pipeline.clean_document", return_value=raw),
            patch("src.ingestion.pipeline.add_section_metadata", return_value=raw),
            patch("src.ingestion.pipeline.detect_and_convert_tables", return_value=raw),
            patch("src.ingestion.pipeline.attach_metadata", return_value=doc),
            patch("src.ingestion.pipeline.chunk_document", return_value=doc),
            patch("src.ingestion.pipeline.embed_chunks", return_value=doc),
            patch("src.ingestion.pipeline.store_chunks", return_value=make_db_report()),
        ):
            return run_pipeline(
                pdf_path=Path("/data/raw/NICE/test.pdf"),
                source_info=FAKE_SOURCE_INFO,
                db_url=None,
                dry_run=dry_run,
                write_debug_artifacts=write_debug,
            )

    def test_returns_report_dict(self) -> None:
        report = self._run()
        for key in ["file", "doc_id", "pages", "chunks", "embeddings_succeeded", "db"]:
            assert key in report

    def test_dry_run_skips_store(self) -> None:
        with (
            patch(
                "src.ingestion.pipeline.extract_raw_document",
                return_value=make_raw_doc(),
            ),
            patch("src.ingestion.pipeline.clean_document", return_value=make_raw_doc()),
            patch(
                "src.ingestion.pipeline.add_section_metadata",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.detect_and_convert_tables",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.attach_metadata",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.chunk_document",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.embed_chunks", return_value=make_embedded_doc()
            ),
            patch("src.ingestion.pipeline.store_chunks") as mock_store,
        ):
            run_pipeline(
                pdf_path=Path("/data/raw/NICE/test.pdf"),
                source_info=FAKE_SOURCE_INFO,
                db_url=None,
                dry_run=True,
                write_debug_artifacts=False,
            )
        mock_store.assert_not_called()

    def test_store_called_when_not_dry_run(self) -> None:
        with (
            patch(
                "src.ingestion.pipeline.extract_raw_document",
                return_value=make_raw_doc(),
            ),
            patch("src.ingestion.pipeline.clean_document", return_value=make_raw_doc()),
            patch(
                "src.ingestion.pipeline.add_section_metadata",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.detect_and_convert_tables",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.attach_metadata",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.chunk_document",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.embed_chunks", return_value=make_embedded_doc()
            ),
            patch(
                "src.ingestion.pipeline.store_chunks", return_value=make_db_report()
            ) as mock_store,
        ):
            run_pipeline(
                pdf_path=Path("/data/raw/NICE/test.pdf"),
                source_info=FAKE_SOURCE_INFO,
                db_url="postgresql://localhost/db",
                dry_run=False,
                write_debug_artifacts=False,
            )
        mock_store.assert_called_once()

    def test_extract_failure_raises_pipeline_error(self) -> None:
        with patch(
            "src.ingestion.pipeline.extract_raw_document",
            side_effect=RuntimeError("corrupt pdf"),
        ):
            with pytest.raises(PipelineError) as exc_info:
                run_pipeline(
                    pdf_path=Path("/data/raw/NICE/test.pdf"),
                    source_info=FAKE_SOURCE_INFO,
                    db_url=None,
                    dry_run=True,
                    write_debug_artifacts=False,
                )
            assert exc_info.value.stage == "EXTRACT"
            assert "corrupt pdf" in exc_info.value.message

    def test_chunk_failure_raises_pipeline_error(self) -> None:
        with (
            patch(
                "src.ingestion.pipeline.extract_raw_document",
                return_value=make_raw_doc(),
            ),
            patch("src.ingestion.pipeline.clean_document", return_value=make_raw_doc()),
            patch(
                "src.ingestion.pipeline.add_section_metadata",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.detect_and_convert_tables",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.attach_metadata",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.chunk_document",
                side_effect=RuntimeError("token exceeded"),
            ),
        ):
            with pytest.raises(PipelineError) as exc_info:
                run_pipeline(
                    pdf_path=Path("/data/raw/NICE/test.pdf"),
                    source_info=FAKE_SOURCE_INFO,
                    db_url=None,
                    dry_run=True,
                    write_debug_artifacts=False,
                )
            assert exc_info.value.stage == "CHUNK"

    def test_report_chunk_count_correct(self) -> None:
        report = self._run()
        assert report["chunks"] == 1

    def test_db_report_zeros_on_dry_run(self) -> None:
        report = self._run(dry_run=True)
        assert report["db"] == {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

    def test_debug_artifacts_written_when_flag_set(self, tmp_path: Path) -> None:
        with (
            patch(
                "src.ingestion.pipeline.extract_raw_document",
                return_value=make_raw_doc(),
            ),
            patch("src.ingestion.pipeline.clean_document", return_value=make_raw_doc()),
            patch(
                "src.ingestion.pipeline.add_section_metadata",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.detect_and_convert_tables",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.attach_metadata",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.chunk_document",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.embed_chunks", return_value=make_embedded_doc()
            ),
            patch("src.ingestion.pipeline.store_chunks", return_value=make_db_report()),
            patch("src.ingestion.pipeline.path_config") as mock_path,
        ):
            mock_path.data_debug = tmp_path
            run_pipeline(
                pdf_path=Path("/data/raw/NICE/test.pdf"),
                source_info=FAKE_SOURCE_INFO,
                db_url=None,
                dry_run=True,
                write_debug_artifacts=True,
            )

    def test_debug_artifacts_not_written_by_default(self, tmp_path: Path) -> None:
        with (
            patch(
                "src.ingestion.pipeline.extract_raw_document",
                return_value=make_raw_doc(),
            ),
            patch("src.ingestion.pipeline.clean_document", return_value=make_raw_doc()),
            patch(
                "src.ingestion.pipeline.add_section_metadata",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.detect_and_convert_tables",
                return_value=make_raw_doc(),
            ),
            patch(
                "src.ingestion.pipeline.attach_metadata",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.chunk_document",
                return_value=make_embedded_doc(),
            ),
            patch(
                "src.ingestion.pipeline.embed_chunks", return_value=make_embedded_doc()
            ),
            patch("src.ingestion.pipeline.store_chunks", return_value=make_db_report()),
            patch("src.ingestion.pipeline.path_config") as mock_path,
        ):
            mock_path.data_debug = tmp_path
            run_pipeline(
                pdf_path=Path("/data/raw/NICE/test.pdf"),
                source_info=FAKE_SOURCE_INFO,
                db_url=None,
                dry_run=True,
                write_debug_artifacts=False,
            )
        assert list(tmp_path.iterdir()) == []


# -----------------------------------------------------------------------
# run_ingestion
# -----------------------------------------------------------------------


class TestRunIngestion:
    def _sources_yaml(self, tmp_path: Path) -> Path:
        f = tmp_path / "sources.yaml"
        f.write_text(
            "NICE:\n"
            "  source_name: NICE\n"
            "  author_org: NICE\n"
            "  specialty: rheumatology\n"
            "  doc_type: guideline\n"
            "  source_url: https://nice.org.uk\n"
        )
        return f

    def test_unknown_source_name_raises(self, tmp_path: Path) -> None:
        sources = tmp_path / "sources.yaml"
        sources.write_text("NICE:\n  source_name: NICE\n")
        with (
            patch(
                "src.ingestion.pipeline.Path",
                side_effect=lambda x: tmp_path / x if "configs" in str(x) else Path(x),
            ),
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
        ):
            with pytest.raises(ValueError, match="Unknown --source-name"):
                run_ingestion(
                    input_path=tmp_path,
                    source_name="UNKNOWN",
                    db_url=None,
                    dry_run=True,
                )

    def test_empty_folder_returns_zero_counts(self, tmp_path: Path) -> None:
        with (
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
        ):
            summary = run_ingestion(
                input_path=tmp_path,
                source_name="NICE",
                db_url=None,
                dry_run=True,
            )
        assert summary["files_scanned"] == 0
        assert summary["files_succeeded"] == 0

    def test_successful_run_increments_counts(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.touch()
        with (
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
            patch(
                "src.ingestion.pipeline.run_pipeline",
                return_value={
                    "file": str(pdf),
                    "doc_id": "abc123",
                    "pages": 2,
                    "chunks": 5,
                    "embeddings_succeeded": 5,
                    "embeddings_failed": 0,
                    "headings_detected": 3,
                    "tables_detected": 1,
                    "db": make_db_report(inserted=5),
                },
            ),
        ):
            summary = run_ingestion(
                input_path=tmp_path,
                source_name="NICE",
                db_url=None,
                dry_run=True,
            )
        assert summary["files_succeeded"] == 1
        assert summary["total_chunks"] == 5
        assert summary["db"]["inserted"] == 5

    def test_pipeline_error_increments_failed(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.touch()
        with (
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
            patch(
                "src.ingestion.pipeline.run_pipeline",
                side_effect=PipelineError("EXTRACT", str(pdf), "corrupt"),
            ),
        ):
            summary = run_ingestion(
                input_path=tmp_path,
                source_name="NICE",
                db_url=None,
                dry_run=True,
            )
        assert summary["files_failed"] == 1
        assert summary["files_succeeded"] == 0

    def test_one_failure_does_not_stop_others(self, tmp_path: Path) -> None:
        pdf1 = tmp_path / "a.pdf"
        pdf2 = tmp_path / "b.pdf"
        pdf1.touch()
        pdf2.touch()

        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PipelineError("EXTRACT", str(pdf1), "corrupt")
            return {
                "file": str(pdf2),
                "doc_id": "abc",
                "pages": 1,
                "chunks": 2,
                "embeddings_succeeded": 2,
                "embeddings_failed": 0,
                "headings_detected": 0,
                "tables_detected": 0,
                "db": make_db_report(inserted=2),
            }

        with (
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
            patch("src.ingestion.pipeline.run_pipeline", side_effect=side_effect),
        ):
            summary = run_ingestion(
                input_path=tmp_path,
                source_name="NICE",
                db_url=None,
                dry_run=True,
            )

        assert summary["files_failed"] == 1
        assert summary["files_succeeded"] == 1
        assert summary["total_chunks"] == 2

    def test_max_files_limits_processing(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"{i}.pdf").touch()

        processed = []

        def side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            processed.append(kwargs.get("pdf_path", args[0]))
            return {
                "file": "x.pdf",
                "doc_id": "abc",
                "pages": 1,
                "chunks": 1,
                "embeddings_succeeded": 1,
                "embeddings_failed": 0,
                "headings_detected": 0,
                "tables_detected": 0,
                "db": make_db_report(),
            }

        with (
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
            patch("src.ingestion.pipeline.run_pipeline", side_effect=side_effect),
        ):
            run_ingestion(
                input_path=tmp_path,
                source_name="NICE",
                db_url=None,
                dry_run=True,
                max_files=2,
            )

        assert len(processed) == 2

    def test_summary_has_all_keys(self, tmp_path: Path) -> None:
        with (
            patch(
                "src.ingestion.pipeline.load_sources",
                return_value={"NICE": FAKE_SOURCE_INFO},
            ),
            patch("src.ingestion.pipeline.load_ingestion_config", return_value={}),
        ):
            summary = run_ingestion(
                input_path=tmp_path,
                source_name="NICE",
                db_url=None,
                dry_run=True,
            )
        for key in [
            "files_scanned",
            "files_succeeded",
            "files_failed",
            "total_chunks",
            "embeddings_succeeded",
            "embeddings_failed",
            "db",
        ]:
            assert key in summary
        for key in ["inserted", "updated", "skipped", "failed"]:
            assert key in summary["db"]
