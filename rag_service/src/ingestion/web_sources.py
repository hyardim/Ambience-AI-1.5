from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_USER_AGENT = "AmbienceRAGGuidelineSync/1.0 (+https://example.invalid/contact)"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
MAX_NICE_CRAWL_DEPTH = 2
MAX_NICE_CRAWL_PAGES = 120

NICE_GUIDELINE_PATH_RE = re.compile(
    r"^/guidance/(ng|cg|qs|ta|ipg|mtg|dg|hst|es)\d+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WebSourceConfig:
    key: str
    source_name: str
    specialty: str
    listing_url: str
    publisher: str
    parser: str


@dataclass(frozen=True)
class DiscoveredDocument:
    canonical_url: str
    title: str
    source_name: str
    specialty: str
    doc_url: str
    publisher: str
    etag: str | None
    last_modified: str | None
    content_length: int | None
    discovered_at: str


WEB_SOURCES: dict[str, WebSourceConfig] = {
    "nice-musculoskeletal": WebSourceConfig(
        key="nice-musculoskeletal",
        source_name="NICE",
        specialty="rheumatology",
        listing_url=(
            "https://www.nice.org.uk/guidance/conditions-and-diseases/"
            "musculoskeletal-conditions"
        ),
        publisher="National Institute for Health and Care Excellence",
        parser="nice",
    ),
    "nice-neurological": WebSourceConfig(
        key="nice-neurological",
        source_name="NICE_NEURO",
        specialty="neurology",
        listing_url=(
            "https://www.nice.org.uk/guidance/conditions-and-diseases/"
            "neurological-conditions"
        ),
        publisher="National Institute for Health and Care Excellence",
        parser="nice",
    ),
    "bsr-guidelines": WebSourceConfig(
        key="bsr-guidelines",
        source_name="BSR",
        specialty="rheumatology",
        listing_url="https://www.rheumatology.org.uk/guidelines",
        publisher="British Society for Rheumatology",
        parser="bsr",
    ),
}


def normalize_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url or "", url)
    parsed = urlparse(absolute)
    path = re.sub(r"//+", "/", parsed.path or "/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def _likely_guideline_link(href: str, text: str) -> bool:
    value = f"{href} {text}".lower()
    keywords = (
        "guideline",
        "guidance",
        "recommendation",
        "arthritis",
        "musculoskeletal",
        "neurology",
        "rheumat",
        "pdf",
    )
    return any(keyword in value for keyword in keywords)


def _extract_candidate_links(html: str, base_url: str, parser: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        text = anchor.get_text(" ", strip=True)
        if not href:
            continue
        normalized = normalize_url(href, base_url=base_url)
        if parser == "nice":
            if "/guidance/" in normalized or normalized.lower().endswith(".pdf"):
                links.append(normalized)
        elif parser == "bsr":
            if _likely_guideline_link(normalized, text):
                links.append(normalized)
        elif _likely_guideline_link(normalized, text):
            links.append(normalized)
    return sorted(set(links))


def _is_nice_guideline_link(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("nice.org.uk") and bool(
        NICE_GUIDELINE_PATH_RE.match(parsed.path)
    )


def _extract_nice_subcategory_links(html: str, listing_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    listing_prefix = normalize_url(listing_url).rstrip("/") + "/"
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        absolute = normalize_url(href, base_url=listing_url)
        if not absolute.startswith(listing_prefix):
            continue
        parsed = urlparse(absolute)
        if not parsed.path.startswith(urlparse(listing_prefix).path):
            continue
        if parsed.path.endswith(".pdf"):
            continue
        links.append(absolute)
    return sorted(set(links))


def _extract_nice_guideline_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        absolute = normalize_url(href, base_url=base_url)
        if _is_nice_guideline_link(absolute):
            links.append(absolute)
    return sorted(set(links))


def _extract_pdf_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        absolute = normalize_url(href, base_url=base_url)
        if absolute.lower().endswith(".pdf") or "pdf" in href.lower():
            urls.append(absolute)
    return sorted(set(urls))


def _extract_page_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    if heading is not None:
        text = heading.get_text(" ", strip=True)
        if text:
            return text
    title = soup.find("title")
    if title is not None:
        text = title.get_text(" ", strip=True)
        if text:
            return text
    return None


class SourceDiscoveryClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._retries = max(1, retries)
        self._backoff_seconds = max(0.1, backoff_seconds)
        self._user_agent = user_agent

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
    ) -> httpx.Response:
        headers = {"User-Agent": self._user_agent}
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self._timeout_seconds,
                    follow_redirects=True,
                )
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return response
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self._retries:
                    break
                await asyncio.sleep(self._backoff_seconds * attempt)
        if last_error is None:
            raise RuntimeError(
                "HTTP request failed without a captured exception")
        raise last_error

    async def _is_allowed_by_robots(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            robots_response = await self._request(client, "GET", robots_url)
        except Exception:
            return True

        if robots_response.status_code >= 400:
            return True

        parser = RobotFileParser()
        parser.parse(robots_response.text.splitlines())
        return parser.can_fetch(self._user_agent, url)

    async def _head_metadata(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[str | None, str | None, int | None]:
        try:
            head = await self._request(client, "HEAD", url)
            if head.status_code >= 400:
                return None, None, None
            content_length = head.headers.get("Content-Length")
            parsed_length = int(
                content_length) if content_length and content_length.isdigit() else None
            return (
                head.headers.get("ETag"),
                head.headers.get("Last-Modified"),
                parsed_length,
            )
        except Exception:
            return None, None, None

    async def discover_source(
        self,
        source: WebSourceConfig,
    ) -> list[DiscoveredDocument]:
        async with httpx.AsyncClient() as client:
            if not await self._is_allowed_by_robots(client, source.listing_url):
                logger.warning(
                    "sync.discovery.skip_robots source=%s listing=%s",
                    source.source_name,
                    source.listing_url,
                )
                return []

            listing_response = await self._request(client, "GET", source.listing_url)
            if listing_response.status_code >= 400:
                logger.warning(
                    "sync.discovery.skip_http source=%s listing=%s status=%s",
                    source.source_name,
                    source.listing_url,
                    listing_response.status_code,
                )
                return []

            if source.parser == "nice":
                candidate_links = await self._discover_nice_candidates(
                    client=client,
                    source=source,
                    listing_html=listing_response.text,
                )
            else:
                candidate_links = _extract_candidate_links(
                    listing_response.text,
                    base_url=source.listing_url,
                    parser=source.parser,
                )

            discovered: dict[str, DiscoveredDocument] = {}
            for candidate in candidate_links:
                if candidate.lower().endswith(".pdf"):
                    title = PathLikeTitle.from_url(candidate)
                    etag, last_modified, content_length = await self._head_metadata(client, candidate)
                    discovered[candidate] = DiscoveredDocument(
                        canonical_url=candidate,
                        title=title,
                        source_name=source.source_name,
                        specialty=source.specialty,
                        doc_url=candidate,
                        publisher=source.publisher,
                        etag=etag,
                        last_modified=last_modified,
                        content_length=content_length,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                    )
                    continue

                try:
                    detail = await self._request(client, "GET", candidate)
                except Exception:
                    continue
                if detail.status_code >= 400:
                    continue

                title = _extract_page_title(
                    detail.text) or PathLikeTitle.from_url(candidate)
                pdf_links = _extract_pdf_links(detail.text, base_url=candidate)
                for pdf_link in pdf_links:
                    etag, last_modified, content_length = await self._head_metadata(client, pdf_link)
                    canonical = normalize_url(candidate)
                    key = f"{source.source_name}|{canonical}|{pdf_link}"
                    discovered[key] = DiscoveredDocument(
                        canonical_url=canonical,
                        title=title,
                        source_name=source.source_name,
                        specialty=source.specialty,
                        doc_url=pdf_link,
                        publisher=source.publisher,
                        etag=etag,
                        last_modified=last_modified,
                        content_length=content_length,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                    )

            return list(discovered.values())

    async def _discover_nice_candidates(
        self,
        *,
        client: httpx.AsyncClient,
        source: WebSourceConfig,
        listing_html: str,
    ) -> list[str]:
        """Discover NICE guideline/detail/PDF candidates via category crawl."""
        start_url = normalize_url(source.listing_url)
        queue: list[tuple[str, int, str]] = [(start_url, 0, listing_html)]
        visited: set[str] = set()
        guideline_links: set[str] = set()
        direct_pdf_links: set[str] = set()

        while queue and len(visited) < MAX_NICE_CRAWL_PAGES:
            page_url, depth, html = queue.pop(0)
            normalized_page = normalize_url(page_url)
            if normalized_page in visited:
                continue
            visited.add(normalized_page)

            for guideline_url in _extract_nice_guideline_links(html, base_url=normalized_page):
                guideline_links.add(guideline_url)

            for pdf_url in _extract_pdf_links(html, base_url=normalized_page):
                if pdf_url.lower().endswith(".pdf"):
                    direct_pdf_links.add(pdf_url)

            if depth >= MAX_NICE_CRAWL_DEPTH:
                continue

            for child_url in _extract_nice_subcategory_links(html, listing_url=start_url):
                if child_url in visited:
                    continue
                try:
                    child_response = await self._request(client, "GET", child_url)
                except Exception:
                    continue
                if child_response.status_code >= 400:
                    continue
                queue.append((child_url, depth + 1, child_response.text))

        logger.info(
            "sync.discovery.nice source=%s visited=%s guideline_links=%s direct_pdfs=%s",
            source.source_name,
            len(visited),
            len(guideline_links),
            len(direct_pdf_links),
        )
        return sorted(guideline_links.union(direct_pdf_links))


class PathLikeTitle:
    @staticmethod
    def from_url(url: str) -> str:
        parsed = urlparse(url)
        segment = parsed.path.strip("/").split("/")[-1] or "guideline"
        segment = re.sub(r"\.pdf$", "", segment, flags=re.IGNORECASE)
        return re.sub(r"[-_]+", " ", segment).strip().title() or "Guideline"
