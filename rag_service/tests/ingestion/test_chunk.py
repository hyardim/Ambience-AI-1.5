from __future__ import annotations

from typing import Any

from src.ingestion.chunk import (
    MAX_CHUNK_TOKENS,
    build_citation,
    chunk_document,
    chunk_section_group,
    clean_chunk_text,
    count_tokens,
    generate_chunk_id,
    group_blocks_by_section,
    make_table_chunk,
    merge_short_sections,
    split_into_sentences,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

LONG_SENTENCE = (
    "This is a detailed clinical recommendation about the management of "
    "rheumatoid arthritis in adult patients. "
)


def make_block(
    text: str = "Body text about clinical guidelines.",
    block_id: int = 0,
    page_number: int = 1,
    block_uid: str = "uid001",
    section_path: list[str] | None = None,
    section_title: str = "Introduction",
    content_type: str = "text",
    include_in_chunks: bool = True,
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "block_uid": block_uid,
        "text": text,
        "page_number": page_number,
        "bbox": [10.0, 100.0, 500.0, 120.0],
        "font_size": 12.0,
        "is_heading": False,
        "include_in_chunks": include_in_chunks,
        "section_path": section_path or ["Introduction"],
        "section_title": section_title,
        "content_type": content_type,
    }


def make_doc_meta(
    doc_id: str = "doc123",
    doc_version: str = "v1",
    title: str = "RA Guidelines",
    source_name: str = "NICE",
    specialty: str = "rheumatology",
    author_org: str = "NICE",
    creation_date: str = "2020-01-01",
    last_updated_date: str = "2024-01-15",
    source_url: str = "https://nice.org.uk",
    ingestion_date: str = "2024-06-01",
) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_version": doc_version,
        "title": title,
        "source_name": source_name,
        "specialty": specialty,
        "author_org": author_org,
        "creation_date": creation_date,
        "last_updated_date": last_updated_date,
        "source_url": source_url,
        "ingestion_date": ingestion_date,
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "doc_type": "guideline",
    }


def make_metadata_doc(
    pages: list[dict[str, Any]] | None = None,
    doc_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if doc_meta is None:
        doc_meta = make_doc_meta()
    if pages is None:
        pages = [{"page_number": 1, "blocks": [make_block()]}]
    return {
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "num_pages": len(pages),
        "needs_ocr": False,
        "doc_meta": doc_meta,
        "pages": pages,
    }


def long_text(n_sentences: int = 60) -> str:
    return LONG_SENTENCE * n_sentences


# -----------------------------------------------------------------------
# count_tokens
# -----------------------------------------------------------------------


class TestCountTokens:
    def test_empty_string(self) -> None:
        assert count_tokens("") == 0

    def test_single_word(self) -> None:
        assert count_tokens("hello") > 0

    def test_longer_text_more_tokens(self) -> None:
        assert count_tokens("hello world foo bar") > count_tokens("hello")

    def test_deterministic(self) -> None:
        text = "The patient was prescribed methotrexate."
        assert count_tokens(text) == count_tokens(text)


# -----------------------------------------------------------------------
# split_into_sentences
# -----------------------------------------------------------------------


class TestSplitIntoSentences:
    def test_single_sentence(self) -> None:
        result = split_into_sentences("This is a sentence.")
        assert len(result) == 1

    def test_multiple_sentences(self) -> None:
        result = split_into_sentences("First sentence. Second sentence. Third.")
        assert len(result) == 3

    def test_empty_string(self) -> None:
        assert split_into_sentences("") == []

    def test_medical_abbreviation_not_split(self) -> None:
        text = (
            "Patients should be monitored regularly. DMARDs are first-line treatment."
        )
        result = split_into_sentences(text)
        assert len(result) == 2

    def test_whitespace_only_filtered(self) -> None:
        assert split_into_sentences("  ") == []


# -----------------------------------------------------------------------
# clean_chunk_text
# -----------------------------------------------------------------------


class TestCleanChunkText:
    def test_strips_whitespace(self) -> None:
        assert clean_chunk_text("  hello  ") == "hello"

    def test_collapses_triple_newlines(self) -> None:
        assert "\n\n\n" not in clean_chunk_text("a\n\n\n\nb")

    def test_preserves_double_newline(self) -> None:
        assert "\n\n" in clean_chunk_text("para one\n\npara two")

    def test_empty_string(self) -> None:
        assert clean_chunk_text("") == ""


# -----------------------------------------------------------------------
# generate_chunk_id
# -----------------------------------------------------------------------


class TestGenerateChunkId:
    def test_returns_16_char_hex(self) -> None:
        cid = generate_chunk_id("doc1", "v1", "some text")
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)

    def test_deterministic(self) -> None:
        assert generate_chunk_id("doc1", "v1", "text") == generate_chunk_id(
            "doc1", "v1", "text"
        )

    def test_different_text_different_id(self) -> None:
        assert generate_chunk_id("doc1", "v1", "text A") != generate_chunk_id(
            "doc1", "v1", "text B"
        )

    def test_different_version_different_id(self) -> None:
        assert generate_chunk_id("doc1", "v1", "text") != generate_chunk_id(
            "doc1", "v2", "text"
        )

    def test_content_based_not_positional(self) -> None:
        assert generate_chunk_id("doc1", "v1", "identical text") == generate_chunk_id(
            "doc1", "v1", "identical text"
        )


# -----------------------------------------------------------------------
# build_citation
# -----------------------------------------------------------------------


class TestBuildCitation:
    def test_all_fields_present(self) -> None:
        citation = build_citation(
            {
                "section_path": ["Treatment"],
                "section_title": "Treatment",
                "page_range": "5-7",
            },
            make_doc_meta(),
        )
        for field in [
            "doc_id",
            "source_name",
            "specialty",
            "title",
            "author_org",
            "creation_date",
            "last_updated_date",
            "section_path",
            "section_title",
            "page_range",
            "source_url",
            "access_date",
        ]:
            assert field in citation

    def test_page_range_set(self) -> None:
        citation = build_citation(
            {"section_path": [], "section_title": "", "page_range": "12-13"},
            make_doc_meta(),
        )
        assert citation["page_range"] == "12-13"

    def test_access_date_from_ingestion_date(self) -> None:
        citation = build_citation(
            {"section_path": [], "section_title": "", "page_range": "1"},
            make_doc_meta(ingestion_date="2024-06-01"),
        )
        assert citation["access_date"] == "2024-06-01"


# -----------------------------------------------------------------------
# make_table_chunk
# -----------------------------------------------------------------------


class TestMakeTableChunk:
    def test_content_type_is_table(self) -> None:
        chunk = make_table_chunk(make_block(content_type="table"), make_doc_meta(), 0)
        assert chunk["content_type"] == "table"

    def test_block_uid_in_block_uids(self) -> None:
        chunk = make_table_chunk(
            make_block(content_type="table", block_uid="tbl001"), make_doc_meta(), 0
        )
        assert "tbl001" in chunk["block_uids"]

    def test_page_start_equals_page_end(self) -> None:
        chunk = make_table_chunk(
            make_block(content_type="table", page_number=5), make_doc_meta(), 0
        )
        assert chunk["page_start"] == 5
        assert chunk["page_end"] == 5

    def test_chunk_id_is_16_hex(self) -> None:
        chunk = make_table_chunk(make_block(content_type="table"), make_doc_meta(), 0)
        assert len(chunk["chunk_id"]) == 16

    def test_citation_present(self) -> None:
        chunk = make_table_chunk(make_block(content_type="table"), make_doc_meta(), 0)
        assert "citation" in chunk
        assert chunk["citation"]["doc_id"] == "doc123"

    def test_token_count_present(self) -> None:
        chunk = make_table_chunk(
            make_block(content_type="table", text="| A | B |\n| 1 | 2 |"),
            make_doc_meta(),
            0,
        )
        assert chunk["token_count"] > 0


# -----------------------------------------------------------------------
# group_blocks_by_section
# -----------------------------------------------------------------------


class TestGroupBlocksBySection:
    def test_single_group(self) -> None:
        blocks = [
            make_block(block_id=0, section_path=["Intro"]),
            make_block(block_id=1, section_path=["Intro"]),
        ]
        assert len(group_blocks_by_section(blocks)) == 1

    def test_two_sections(self) -> None:
        blocks = [
            make_block(block_id=0, section_path=["Intro"]),
            make_block(block_id=1, section_path=["Methods"]),
        ]
        assert len(group_blocks_by_section(blocks)) == 2

    def test_interleaved_not_merged(self) -> None:
        blocks = [
            make_block(block_id=0, section_path=["Intro"]),
            make_block(block_id=1, section_path=["Methods"]),
            make_block(block_id=2, section_path=["Intro"]),
        ]
        assert len(group_blocks_by_section(blocks)) == 3

    def test_empty_blocks(self) -> None:
        assert group_blocks_by_section([]) == []


# -----------------------------------------------------------------------
# merge_short_sections
# -----------------------------------------------------------------------


class TestMergeShortSections:
    def _short(self, section: str, uid: str) -> dict[str, Any]:
        return make_block(
            text="Short.", block_uid=uid, section_path=[section], section_title=section
        )

    def _long(self, section: str, uid: str) -> dict[str, Any]:
        return make_block(
            text=long_text(15),
            block_uid=uid,
            section_path=[section],
            section_title=section,
        )

    def test_short_merged_with_next(self) -> None:
        result = merge_short_sections(
            [[self._short("A", "u1")], [self._long("B", "u2")]]
        )
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_long_not_merged(self) -> None:
        result = merge_short_sections(
            [[self._long("A", "u1")], [self._long("B", "u2")]]
        )
        assert len(result) == 2

    def test_short_at_end_stays_standalone(self) -> None:
        result = merge_short_sections(
            [[self._long("A", "u1")], [self._short("B", "u2")]]
        )
        assert len(result) == 2

    def test_table_not_merged_into(self) -> None:
        table = make_block(
            text="| A | B |\n| 1 | 2 |",
            content_type="table",
            block_uid="t1",
            section_path=["T"],
        )
        result = merge_short_sections([[self._short("A", "u1")], [table]])
        assert len(result) == 2

    def test_empty_groups(self) -> None:
        assert merge_short_sections([]) == []

    def test_max_merge_respected(self) -> None:
        groups = [[self._short(s, f"u{i}")] for i, s in enumerate(["A", "B", "C", "D"])]
        result = merge_short_sections(groups)
        assert len(result) <= len(groups)


# -----------------------------------------------------------------------
# chunk_section_group
# -----------------------------------------------------------------------


class TestChunkSectionGroup:
    def test_short_group_one_chunk(self) -> None:
        chunks, _ = chunk_section_group(
            [make_block(text="Short text.", block_uid="u1")], make_doc_meta(), 0, []
        )
        assert len(chunks) == 1

    def test_long_group_multiple_chunks(self) -> None:
        chunks, _ = chunk_section_group(
            [make_block(text=long_text(60), block_uid="u1")], make_doc_meta(), 0, []
        )
        assert len(chunks) > 1

    def test_all_within_token_limit(self) -> None:
        chunks, _ = chunk_section_group(
            [make_block(text=long_text(60), block_uid="u1")], make_doc_meta(), 0, []
        )
        for chunk in chunks:
            assert chunk["token_count"] <= MAX_CHUNK_TOKENS

    def test_chunk_index_starts_at_offset(self) -> None:
        chunks, _ = chunk_section_group(
            [make_block(text="Some text.", block_uid="u1")], make_doc_meta(), 5, []
        )
        assert chunks[0]["chunk_index"] == 5

    def test_no_overlap_returned_across_boundary(self) -> None:
        _, returned_overlap = chunk_section_group(
            [make_block(text="Some content.", block_uid="u1")], make_doc_meta(), 0, []
        )
        assert returned_overlap == []

    def test_block_uids_in_chunk(self) -> None:
        chunks, _ = chunk_section_group(
            [make_block(text="Some text.", block_uid="abc123")], make_doc_meta(), 0, []
        )
        assert "abc123" in chunks[0]["block_uids"]

    def test_page_start_page_end_set(self) -> None:
        blocks = [
            make_block(text="Page one.", block_uid="u1", page_number=3),
            make_block(text="Page two.", block_uid="u2", page_number=4),
        ]
        chunks, _ = chunk_section_group(blocks, make_doc_meta(), 0, [])
        assert min(c["page_start"] for c in chunks) == 3

    def test_empty_blocks_returns_empty(self) -> None:
        chunks, overlap = chunk_section_group([], make_doc_meta(), 0, [])
        assert chunks == []
        assert overlap == []

    def test_citation_fields_complete(self) -> None:
        chunks, _ = chunk_section_group(
            [make_block(text="Clinical content.", block_uid="u1")],
            make_doc_meta(),
            0,
            [],
        )
        citation = chunks[0]["citation"]
        for field in [
            "doc_id",
            "source_name",
            "specialty",
            "title",
            "author_org",
            "creation_date",
            "last_updated_date",
            "section_path",
            "section_title",
            "page_range",
            "source_url",
            "access_date",
        ]:
            assert field in citation

    def test_block_with_empty_text_skipped(self) -> None:
        # covers the `if not text: continue` guard (line 281)
        blocks = [
            make_block(text="", block_uid="empty"),
            make_block(text="Real content.", block_uid="real"),
        ]
        chunks, _ = chunk_section_group(blocks, make_doc_meta(), 0, [])
        assert len(chunks) == 1
        assert "empty" not in chunks[0]["block_uids"]

    def test_all_empty_text_blocks_returns_empty(self) -> None:
        # covers the `if not sentence_block_pairs: return [], []` guard (line 286)
        blocks = [
            make_block(text="", block_uid="e1"),
            make_block(text="   ", block_uid="e2"),
        ]
        chunks, overlap = chunk_section_group(blocks, make_doc_meta(), 0, [])
        assert chunks == []
        assert overlap == []

    def test_build_text_chunk_empty_contributing_blocks_returns_none(self) -> None:
        from src.ingestion.chunk import _build_text_chunk

        result = _build_text_chunk(
            sentences=["Some sentence."],
            contributing_blocks=[],
            doc_meta=make_doc_meta(),
            chunk_index=0,
        )
        assert result is None


# -----------------------------------------------------------------------
# chunk_document (integration)
# -----------------------------------------------------------------------


class TestChunkDocument:
    def test_chunks_key_present(self) -> None:
        assert "chunks" in chunk_document(make_metadata_doc())

    def test_excluded_blocks_not_in_chunks(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(
                        text="Authors: Dr Smith",
                        include_in_chunks=False,
                        block_uid="excluded1",
                    ),
                    make_block(
                        text="Clinical content.",
                        include_in_chunks=True,
                        block_uid="included1",
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        all_uids = [uid for c in result["chunks"] for uid in c["block_uids"]]
        assert "excluded1" not in all_uids
        assert "included1" in all_uids

    def test_table_becomes_one_chunk(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(
                        text="| Drug | Dose |\n| MTX | 7.5mg |",
                        content_type="table",
                        block_uid="tbl1",
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        table_chunks = [c for c in result["chunks"] if c["content_type"] == "table"]
        assert len(table_chunks) == 1
        assert table_chunks[0]["block_uids"] == ["tbl1"]

    def test_table_not_split(self) -> None:
        big_table = ("| " + " | ".join(["Col"] * 5) + " |\n") + (
            "| " + " | ".join(["data"] * 5) + " |\n"
        ) * 50
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(
                        text=big_table, content_type="table", block_uid="bigtbl"
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        assert len([c for c in result["chunks"] if c["content_type"] == "table"]) == 1

    def test_long_section_multiple_chunks(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(text=long_text(60), block_uid="long1"),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        assert len([c for c in result["chunks"] if c["content_type"] == "text"]) > 1

    def test_all_text_chunks_within_token_limit(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(text=long_text(60), block_uid="long1"),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        for chunk in result["chunks"]:
            if chunk["content_type"] == "text":
                assert chunk["token_count"] <= MAX_CHUNK_TOKENS

    def test_chunk_ids_deterministic(self) -> None:
        doc = make_metadata_doc()
        ids1 = [c["chunk_id"] for c in chunk_document(doc)["chunks"]]
        ids2 = [c["chunk_id"] for c in chunk_document(doc)["chunks"]]
        assert ids1 == ids2

    def test_chunk_index_sequential(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(text=long_text(60), block_uid="u1"),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        indices = [c["chunk_index"] for c in result["chunks"]]
        assert indices == list(range(len(indices)))

    def test_page_start_page_end_correct(self) -> None:
        pages = [
            {
                "page_number": 3,
                "blocks": [
                    make_block(
                        text="Content on page 3.", page_number=3, block_uid="u1"
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        for chunk in result["chunks"]:
            assert chunk["page_start"] >= 3

    def test_block_uids_populated(self) -> None:
        for chunk in chunk_document(make_metadata_doc())["chunks"]:
            assert len(chunk["block_uids"]) > 0

    def test_citation_complete_on_all_chunks(self) -> None:
        for chunk in chunk_document(make_metadata_doc())["chunks"]:
            for field in [
                "doc_id",
                "source_name",
                "specialty",
                "title",
                "author_org",
                "creation_date",
                "last_updated_date",
                "section_path",
                "section_title",
                "page_range",
                "source_url",
                "access_date",
            ]:
                assert field in chunk["citation"]

    def test_no_overlap_across_section_boundary(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(
                        text=long_text(10),
                        block_uid="s1",
                        section_path=["Section 1"],
                        section_title="Section 1",
                    ),
                    make_block(
                        text=long_text(10),
                        block_uid="s2",
                        section_path=["Section 2"],
                        section_title="Section 2",
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        s1_chunks = [c for c in result["chunks"] if c["section_title"] == "Section 1"]
        s2_chunks = [c for c in result["chunks"] if c["section_title"] == "Section 2"]
        if s1_chunks and s2_chunks:
            assert s1_chunks[-1]["section_path"] != s2_chunks[0]["section_path"]

    def test_empty_document_returns_empty_chunks(self) -> None:
        assert chunk_document(make_metadata_doc(pages=[]))["chunks"] == []

    def test_original_doc_fields_preserved(self) -> None:
        doc = make_metadata_doc()
        result = chunk_document(doc)
        assert "doc_meta" in result
        assert "pages" in result
        assert result["source_path"] == doc["source_path"]

    def test_short_section_merged(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(
                        text="Short.",
                        block_uid="short1",
                        section_path=["Short Section"],
                        section_title="Short Section",
                    ),
                    make_block(
                        text=long_text(10),
                        block_uid="long1",
                        section_path=["Long Section"],
                        section_title="Long Section",
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        all_text = " ".join(c["text"] for c in result["chunks"])
        assert "Short." in all_text

    def test_short_section_at_end_standalone(self) -> None:
        pages = [
            {
                "page_number": 1,
                "blocks": [
                    make_block(
                        text=long_text(10),
                        block_uid="long1",
                        section_path=["Long Section"],
                        section_title="Long Section",
                    ),
                    make_block(
                        text="Short final note.",
                        block_uid="short1",
                        section_path=["End Note"],
                        section_title="End Note",
                    ),
                ],
            }
        ]
        result = chunk_document(make_metadata_doc(pages=pages))
        all_text = " ".join(c["text"] for c in result["chunks"])
        assert "Short final note." in all_text
