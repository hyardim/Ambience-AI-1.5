from __future__ import annotations

import asyncio

import httpx

from src.ingestion.web_sources import (
    WEB_SOURCES,
    SourceDiscoveryClient,
    _extract_candidate_links,
    _extract_pdf_links,
    normalize_url,
)


def _response(url: str, text: str = "", status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code=status_code, request=request, text=text)


def test_normalize_url_removes_fragment_and_keeps_query() -> None:
    normalized = normalize_url("/a//b/file.pdf?x=1#frag", base_url="https://Example.com")
    assert normalized == "https://example.com/a/b/file.pdf?x=1"


def test_extract_candidate_links_for_nice() -> None:
    html = """
    <a href=\"/guidance/ng193\">Guideline 1</a>
    <a href=\"https://cdn.example.com/file.pdf\">PDF</a>
    <a href=\"/about\">About</a>
    """
    links = _extract_candidate_links(
        html,
        base_url="https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions",
        parser="nice",
    )
    assert "https://www.nice.org.uk/guidance/ng193" in links
    assert "https://cdn.example.com/file.pdf" in links
    assert all("/about" not in link for link in links)


def test_extract_pdf_links_from_detail_page() -> None:
    html = """
    <a href=\"/guidance/ng193/resources/ra-guideline-pdf-123.pdf\">Download PDF</a>
    <a href=\"/guidance/ng193\">Back</a>
    """
    links = _extract_pdf_links(html, base_url="https://www.nice.org.uk/guidance/ng193")
    assert links == [
        "https://www.nice.org.uk/guidance/ng193/resources/ra-guideline-pdf-123.pdf"
    ]


def test_discover_source_finds_detail_and_pdf_links(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)

    listing_html = "<a href='/guidance/ng193'>RA guideline</a>"
    detail_html = """
    <html><head><title>Rheumatoid arthritis in adults</title></head>
    <body><a href='/guidance/ng193/resources/full-guideline.pdf'>PDF</a></body></html>
    """

    async def fake_request(
        client: httpx.AsyncClient, method: str, url: str
    ) -> httpx.Response:
        if "musculoskeletal-conditions" in url and method == "GET":
            return _response(url, listing_html)
        if url.endswith("/guidance/ng193") and method == "GET":
            return _response(url, detail_html)
        return _response(url)

    async def fake_robots(client: httpx.AsyncClient, url: str) -> bool:
        return True

    async def fake_head(
        client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None, int | None]:
        return ("etag-1", "Wed, 01 Jan 2025 00:00:00 GMT", 12345)

    monkeypatch.setattr(discovery, "_request", fake_request)
    monkeypatch.setattr(discovery, "_is_allowed_by_robots", fake_robots)
    monkeypatch.setattr(discovery, "_head_metadata", fake_head)

    docs = asyncio.run(discovery.discover_source(source))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.source_name == "NICE"
    assert doc.specialty == "rheumatology"
    assert doc.canonical_url == "https://www.nice.org.uk/guidance/ng193"
    assert doc.doc_url.endswith("full-guideline.pdf")
    assert doc.etag == "etag-1"
