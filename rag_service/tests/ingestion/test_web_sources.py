from __future__ import annotations

import asyncio

import httpx
import pytest

import src.ingestion.web_sources as web_sources_module
from src.ingestion.web_sources import (
    WEB_SOURCES,
    SourceDiscoveryClient,
    _extract_candidate_links,
    _extract_nice_guideline_links,
    _extract_nice_subcategory_links,
    _extract_page_title,
    _extract_pdf_links,
    _likely_guideline_link,
    normalize_url,
)


def _response(url: str, text: str = "", status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code=status_code, request=request, text=text)


def test_normalize_url_removes_fragment_and_keeps_query() -> None:
    normalized = normalize_url(
        "/a//b/file.pdf?x=1#frag", base_url="https://Example.com"
    )
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


def test_discover_source_crawls_nice_subcategories(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)

    listing_html = (
        "<a href='/guidance/conditions-and-diseases/musculoskeletal-conditions/"
        "arthritis'>Arthritis</a>"
    )
    subcategory_html = "<a href='/guidance/ng100'>RA guideline</a>"
    detail_html = "<a href='/guidance/ng100/resources/ng100-pdf.pdf'>PDF</a>"

    async def fake_request(
        client: httpx.AsyncClient, method: str, url: str
    ) -> httpx.Response:
        if method != "GET":
            return _response(url)
        if url.endswith("musculoskeletal-conditions"):
            return _response(url, listing_html)
        if url.endswith("musculoskeletal-conditions/arthritis"):
            return _response(url, subcategory_html)
        if url.endswith("/guidance/ng100"):
            return _response(url, detail_html)
        return _response(url)

    async def fake_robots(client: httpx.AsyncClient, url: str) -> bool:
        return True

    async def fake_head(
        client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None, int | None]:
        return ("etag-sub", "Wed, 01 Jan 2025 00:00:00 GMT", 2222)

    monkeypatch.setattr(discovery, "_request", fake_request)
    monkeypatch.setattr(discovery, "_is_allowed_by_robots", fake_robots)
    monkeypatch.setattr(discovery, "_head_metadata", fake_head)

    docs = asyncio.run(discovery.discover_source(source))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.canonical_url == "https://www.nice.org.uk/guidance/ng100"
    assert doc.doc_url.endswith("ng100-pdf.pdf")


def test_likely_guideline_link_negative_case() -> None:
    assert _likely_guideline_link("/about", "Company profile") is False


def test_extract_candidate_links_for_bsr_and_generic() -> None:
    html = """
    <a href="/guidelines/ra">Rheumatology guideline</a>
    <a href="/news">News</a>
    """
    bsr_links = _extract_candidate_links(
        html, base_url="https://example.org", parser="bsr"
    )
    generic_links = _extract_candidate_links(
        html, base_url="https://example.org", parser="other"
    )
    assert bsr_links == ["https://example.org/guidelines/ra"]
    assert generic_links == ["https://example.org/guidelines/ra"]


def test_extract_helpers_ignore_empty_hrefs() -> None:
    html = """
    <a href="">empty</a>
    <a>No href</a>
    <a href="/guidance/ng2">good</a>
    <a href="/x.pdf">pdf</a>
    """
    assert _extract_candidate_links(html, "https://www.nice.org.uk", "nice") == [
        "https://www.nice.org.uk/guidance/ng2",
        "https://www.nice.org.uk/x.pdf",
    ]
    assert _extract_nice_guideline_links(html, "https://www.nice.org.uk") == [
        "https://www.nice.org.uk/guidance/ng2"
    ]
    assert _extract_pdf_links(html, "https://www.nice.org.uk") == [
        "https://www.nice.org.uk/x.pdf"
    ]


def test_extract_nice_helpers_and_page_title_fallbacks() -> None:
    html = """
    <a href="/guidance/conditions-and-diseases/musculoskeletal-conditions/
    arthritis">sub</a>
    <a href="/guidance/ng2">valid guideline</a>
    <a href="https://elsewhere.org/guidance/ng100">external</a>
    <h1>Primary Heading</h1>
    <title>Fallback Title</title>
    """
    subs = _extract_nice_subcategory_links(
        html,
        listing_url="https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions",
    )
    guidelines = _extract_nice_guideline_links(
        html,
        base_url="https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions",
    )
    title = _extract_page_title(html)
    none_title = _extract_page_title("<html><body>No title</body></html>")

    assert subs
    assert "https://www.nice.org.uk/guidance/ng2" in guidelines
    assert title == "Primary Heading"
    assert none_title is None


def test_request_retries_then_raises_transport_error(monkeypatch) -> None:
    discovery = SourceDiscoveryClient(retries=2, backoff_seconds=0.01)

    class FailingClient:
        async def request(self, *args, **kwargs):
            del args, kwargs
            raise httpx.TransportError("boom")

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(httpx.TransportError):
        asyncio.run(
            discovery._request(
                FailingClient(),
                "GET",
                "https://example.org",
            )
        )


def test_request_raises_http_status_error_after_retry(monkeypatch) -> None:
    discovery = SourceDiscoveryClient(retries=2, backoff_seconds=0.01)

    class ServerErrorClient:
        async def request(self, method: str, url: str, **kwargs):
            del method, kwargs
            req = httpx.Request("GET", url)
            return httpx.Response(500, request=req)

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            discovery._request(ServerErrorClient(), "GET", "https://example.org")
        )


def test_request_runtime_error_when_retry_loop_never_runs() -> None:
    discovery = SourceDiscoveryClient(retries=1)
    discovery._retries = 0

    class NeverCalledClient:
        async def request(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("should not be called")

    with pytest.raises(RuntimeError):
        asyncio.run(discovery._request(NeverCalledClient(), "GET", "https://x"))


def test_request_returns_response_on_success() -> None:
    discovery = SourceDiscoveryClient(retries=1)

    class OkClient:
        async def request(self, method: str, url: str, **kwargs):
            del method, kwargs
            req = httpx.Request("GET", url)
            return httpx.Response(200, request=req, text="ok")

    response = asyncio.run(discovery._request(OkClient(), "GET", "https://x"))
    assert response.status_code == 200


def test_is_allowed_by_robots_handles_errors_and_disallow(monkeypatch) -> None:
    discovery = SourceDiscoveryClient(retries=1)

    async def fail_request(client, method: str, url: str):
        del client, method, url
        raise RuntimeError("no robots")

    monkeypatch.setattr(discovery, "_request", fail_request)
    assert (
        asyncio.run(
            discovery._is_allowed_by_robots(
                httpx.AsyncClient(), "https://example.org/path"
            )
        )
        is True
    )

    async def missing_robots(client, method: str, url: str):
        del client, method
        return _response(url, "", status_code=404)

    monkeypatch.setattr(discovery, "_request", missing_robots)
    assert (
        asyncio.run(
            discovery._is_allowed_by_robots(
                httpx.AsyncClient(), "https://example.org/path"
            )
        )
        is True
    )

    async def disallow_robots(client, method: str, url: str):
        del client, method
        return _response(url, "User-agent: *\nDisallow: /path")

    monkeypatch.setattr(discovery, "_request", disallow_robots)
    assert (
        asyncio.run(
            discovery._is_allowed_by_robots(
                httpx.AsyncClient(), "https://example.org/path"
            )
        )
        is False
    )


def test_head_metadata_handles_error_paths(monkeypatch) -> None:
    discovery = SourceDiscoveryClient(retries=1)

    async def response_404(client, method: str, url: str):
        del client, method
        return _response(url, "", status_code=404)

    monkeypatch.setattr(discovery, "_request", response_404)
    assert asyncio.run(
        discovery._head_metadata(httpx.AsyncClient(), "https://example.org/file.pdf")
    ) == (None, None, None)

    async def response_bad_length(client, method: str, url: str):
        del client, method
        req = httpx.Request("HEAD", url)
        return httpx.Response(
            200,
            request=req,
            headers={"ETag": "e", "Last-Modified": "l", "Content-Length": "abc"},
        )

    monkeypatch.setattr(discovery, "_request", response_bad_length)
    assert asyncio.run(
        discovery._head_metadata(httpx.AsyncClient(), "https://example.org/file.pdf")
    ) == ("e", "l", None)

    async def response_error(client, method: str, url: str):
        del client, method, url
        raise RuntimeError("head failed")

    monkeypatch.setattr(discovery, "_request", response_error)
    assert asyncio.run(
        discovery._head_metadata(httpx.AsyncClient(), "https://example.org/file.pdf")
    ) == (None, None, None)


def test_discover_source_handles_skip_and_detail_errors(monkeypatch) -> None:
    source = WEB_SOURCES["bsr-guidelines"]
    discovery = SourceDiscoveryClient(retries=1)

    async def deny_robots(client: httpx.AsyncClient, url: str) -> bool:
        del client, url
        return False

    monkeypatch.setattr(discovery, "_is_allowed_by_robots", deny_robots)
    docs = asyncio.run(discovery.discover_source(source))
    assert docs == []

    async def allow_robots(client: httpx.AsyncClient, url: str) -> bool:
        del client, url
        return True

    async def listing_http_error(client: httpx.AsyncClient, method: str, url: str):
        return _response(url, "", status_code=500 if method == "GET" else 200)

    monkeypatch.setattr(discovery, "_is_allowed_by_robots", allow_robots)
    monkeypatch.setattr(discovery, "_request", listing_http_error)
    docs = asyncio.run(discovery.discover_source(source))
    assert docs == []


def test_discover_source_non_nice_parser_handles_detail_errors(monkeypatch) -> None:
    source = WEB_SOURCES["bsr-guidelines"]
    discovery = SourceDiscoveryClient(retries=1)

    async def allow_robots(client: httpx.AsyncClient, url: str) -> bool:
        del client, url
        return True

    listing_html = """
    <a href='/detail'>Guideline detail</a>
    <a href='/direct.pdf'>Direct PDF</a>
    """

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client
        if method == "HEAD":
            req = httpx.Request("HEAD", url)
            return httpx.Response(
                200,
                request=req,
                headers={"ETag": "e", "Last-Modified": "l", "Content-Length": "12"},
            )
        if url.endswith("/guidelines"):
            return _response(url, listing_html)
        if url.endswith("/detail"):
            raise RuntimeError("detail error")
        return _response(url, "", status_code=404)

    monkeypatch.setattr(discovery, "_is_allowed_by_robots", allow_robots)
    monkeypatch.setattr(discovery, "_request", fake_request)
    docs = asyncio.run(discovery.discover_source(source))
    assert len(docs) == 1
    assert docs[0].doc_url.endswith("direct.pdf")


def test_discover_source_non_nice_parser_skips_detail_http_error(monkeypatch) -> None:
    source = WEB_SOURCES["bsr-guidelines"]
    discovery = SourceDiscoveryClient(retries=1)

    async def allow_robots(client: httpx.AsyncClient, url: str) -> bool:
        del client, url
        return True

    listing_html = "<a href='/detail-guideline'>Guideline detail</a>"

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client
        if method == "HEAD":
            return _response(url)
        if url.endswith("/guidelines"):
            return _response(url, listing_html)
        return _response(url, "", status_code=404)

    monkeypatch.setattr(discovery, "_is_allowed_by_robots", allow_robots)
    monkeypatch.setattr(discovery, "_request", fake_request)
    docs = asyncio.run(discovery.discover_source(source))
    assert docs == []


def test_discover_nice_candidates_handles_child_errors(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)
    listing_html = (
        "<a href='/guidance/conditions-and-diseases/musculoskeletal-conditions/"
        "arthritis'>"
        "Sub</a>"
    )

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client, method
        if url.endswith("/arthritis"):
            raise RuntimeError("fetch failed")
        return _response(url, "", status_code=500)

    monkeypatch.setattr(discovery, "_request", fake_request)

    async def run() -> list[str]:
        async with httpx.AsyncClient() as client:
            return await discovery._discover_nice_candidates(
                client=client,
                source=source,
                listing_html=listing_html,
            )

    assert asyncio.run(run()) == []


def test_discover_nice_candidates_handles_duplicates_depth_and_404(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)

    listing_html = (
        "<a href='/guidance/ng2'>Guideline</a>"
        "<a href='/docs/x.pdf'>Pdf</a>"
        "<a href='/guidance/conditions-and-diseases/musculoskeletal-conditions/"
        "child'>Child</a>"
    )
    child_html = (
        "<a href='/guidance/conditions-and-diseases/musculoskeletal-conditions/"
        "child'>Child</a>"
    )

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client
        if method != "GET":
            return _response(url)
        if url.endswith("/child"):
            return _response(url, child_html)
        if url.endswith("/missing"):
            return _response(url, "", status_code=404)
        return _response(url, listing_html)

    monkeypatch.setattr(discovery, "_request", fake_request)

    async def run() -> list[str]:
        async with httpx.AsyncClient() as client:
            return await discovery._discover_nice_candidates(
                client=client,
                source=source,
                listing_html=listing_html,
            )

    links = asyncio.run(run())
    assert "https://www.nice.org.uk/guidance/ng2" in links
    assert "https://www.nice.org.uk/docs/x.pdf" in links


def test_extract_nice_subcategory_links_branch_coverage(monkeypatch) -> None:
    html = """
    <a href="">empty</a>
    <a href="/guidance/conditions-and-diseases/musculoskeletal-conditions/a.pdf">pdf</a>
    <a href="/guidance/conditions-and-diseases/musculoskeletal-conditions/ok">ok</a>
    """

    original_urlparse = web_sources_module.urlparse

    def fake_urlparse(value: str):
        parsed = original_urlparse(value)
        if value.endswith("musculoskeletal-conditions/"):
            return parsed._replace(path="/different")
        return parsed

    monkeypatch.setattr(web_sources_module, "urlparse", fake_urlparse)
    links = _extract_nice_subcategory_links(
        html,
        listing_url="https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions",
    )
    assert links == []


def test_extract_nice_subcategory_links_skips_pdf_children() -> None:
    html = (
        "<a href='/guidance/conditions-and-diseases/musculoskeletal-conditions/"
        "file.pdf'>pdf</a>"
        "<a href='/guidance/conditions-and-diseases/musculoskeletal-conditions/"
        "ok'>ok</a>"
    )
    links = _extract_nice_subcategory_links(
        html,
        listing_url="https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions",
    )
    assert links == [
        "https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions/ok"
    ]


def test_discover_nice_candidates_hits_duplicate_visited_branch(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)

    monkeypatch.setattr(
        web_sources_module,
        "_extract_nice_subcategory_links",
        lambda html, listing_url: [
            "https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions/child",
            "https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions/child",
        ],
    )
    monkeypatch.setattr(
        web_sources_module,
        "_extract_nice_guideline_links",
        lambda html, base_url: [],
    )
    monkeypatch.setattr(
        web_sources_module,
        "_extract_pdf_links",
        lambda html, base_url: [],
    )

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client, method
        return _response(url, "<html></html>")

    monkeypatch.setattr(discovery, "_request", fake_request)

    async def run() -> list[str]:
        async with httpx.AsyncClient() as client:
            return await discovery._discover_nice_candidates(
                client=client,
                source=source,
                listing_html="<html></html>",
            )

    assert asyncio.run(run()) == []


def test_discover_nice_candidates_hits_depth_and_child_404(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)

    monkeypatch.setattr(web_sources_module, "MAX_NICE_CRAWL_DEPTH", 0)
    monkeypatch.setattr(
        web_sources_module,
        "_extract_nice_subcategory_links",
        lambda html, listing_url: [
            "https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions/missing"
        ],
    )

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client, method
        return _response(url, "", status_code=404)

    monkeypatch.setattr(discovery, "_request", fake_request)

    async def run() -> list[str]:
        async with httpx.AsyncClient() as client:
            return await discovery._discover_nice_candidates(
                client=client,
                source=source,
                listing_html="<a href='/x'>x</a>",
            )

    assert asyncio.run(run()) == []


def test_discover_nice_candidates_child_404_is_skipped(monkeypatch) -> None:
    source = WEB_SOURCES["nice-musculoskeletal"]
    discovery = SourceDiscoveryClient(retries=1)

    monkeypatch.setattr(
        web_sources_module,
        "_extract_nice_subcategory_links",
        lambda html, listing_url: [
            "https://www.nice.org.uk/guidance/conditions-and-diseases/musculoskeletal-conditions/missing"
        ],
    )
    monkeypatch.setattr(
        web_sources_module,
        "_extract_nice_guideline_links",
        lambda html, base_url: [],
    )
    monkeypatch.setattr(
        web_sources_module,
        "_extract_pdf_links",
        lambda html, base_url: [],
    )

    async def fake_request(client: httpx.AsyncClient, method: str, url: str):
        del client, method
        return _response(url, "", status_code=404)

    monkeypatch.setattr(discovery, "_request", fake_request)

    async def run() -> list[str]:
        async with httpx.AsyncClient() as client:
            return await discovery._discover_nice_candidates(
                client=client,
                source=source,
                listing_html="<a href='/x'>x</a>",
            )

    assert asyncio.run(run()) == []
