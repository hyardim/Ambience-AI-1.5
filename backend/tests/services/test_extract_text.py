"""
Tests for the _extract_text() helper in chat_service:
covers plain text, unknown type, missing file, minimal PDF, and corrupt PDF.
"""

_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n"
    b"0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


class TestExtractText:
    def test_plain_text_file_returns_content(self, tmp_path):
        from src.services.chat_service import _extract_text

        f = tmp_path / "note.txt"
        f.write_text("Patient has RRMS. New T2 lesion on MRI.")
        result = _extract_text(str(f), "text/plain")
        assert "RRMS" in result
        assert "T2 lesion" in result

    def test_none_type_reads_as_plain_text(self, tmp_path):
        from src.services.chat_service import _extract_text

        f = tmp_path / "data.dat"
        f.write_text("Clinical observation data.")
        result = _extract_text(str(f), None)
        assert "Clinical observation" in result

    def test_unknown_mime_type_reads_as_plain_text(self, tmp_path):
        from src.services.chat_service import _extract_text

        f = tmp_path / "report.xyz"
        f.write_text("Discharge summary content.")
        result = _extract_text(str(f), "application/octet-stream")
        assert "Discharge summary" in result

    def test_nonexistent_file_returns_empty_string(self):
        from src.services.chat_service import _extract_text

        result = _extract_text("/nonexistent/path/file.txt", "text/plain")
        assert result == ""

    def test_pdf_mime_type_dispatches_to_pypdf(self, tmp_path):
        from src.services.chat_service import _extract_text

        f = tmp_path / "test.pdf"
        f.write_bytes(_PDF_BYTES)
        result = _extract_text(str(f), "application/pdf")
        assert isinstance(result, str)

    def test_pdf_content_type_with_charset_param(self, tmp_path):
        """MIME types like 'application/pdf; charset=utf-8' still route to pypdf."""
        from src.services.chat_service import _extract_text

        f = tmp_path / "test.pdf"
        f.write_bytes(_PDF_BYTES)
        result = _extract_text(str(f), "application/pdf; charset=utf-8")
        assert isinstance(result, str)

    def test_corrupt_pdf_returns_empty_string(self, tmp_path):
        from src.services.chat_service import _extract_text

        f = tmp_path / "corrupt.pdf"
        f.write_bytes(b"this is not a pdf")
        result = _extract_text(str(f), "application/pdf")
        assert result == ""

    def test_empty_text_file_returns_empty_string(self, tmp_path):
        from src.services.chat_service import _extract_text

        f = tmp_path / "empty.txt"
        f.write_text("")
        result = _extract_text(str(f), "text/plain")
        assert result == ""
