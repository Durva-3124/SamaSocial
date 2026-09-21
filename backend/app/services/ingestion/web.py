"""Webpage ingestion with SSRF protection and heading-based chunking."""
import logging
import re
from urllib.parse import urlparse

import httpx
import trafilatura

from app.core.errors import AppError
from app.core.url_safety import validate_public_url
from app.models.chunk import Chunk, Locator
from app.services.chunking import split_text
from app.services.ingestion.base import IngestResult

logger = logging.getLogger(__name__)

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_FETCH_TIMEOUT = 15.0
_MAX_REDIRECTS = 3
_MIN_CONTENT_CHARS = 200
_USER_AGENT = (
    "Mozilla/5.0 (compatible; SamasocialBot/1.0; +https://github.com/Durva-3124/SamaSocial)"
)
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _split_by_headings(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) sections.

    Returns list of (heading_label, section_text) pairs.
    The heading_label is the nearest heading above the text, or "" for the preamble.
    """
    parts = _HEADING_RE.split(markdown)
    # parts alternates: [pre_text, heading1, body1, heading2, body2, ...]
    sections: list[tuple[str, str]] = []

    # preamble before first heading
    if parts[0].strip():
        sections.append(("", parts[0].strip()))

    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if heading or body:
            sections.append((heading, body))

    return sections


async def ingest_web(source_id: str, url: str) -> IngestResult:
    """Fetch a webpage and ingest it into heading-based chunks."""
    validate_public_url(url)

    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT,
            max_redirects=_MAX_REDIRECTS,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as resp:
                # Re-validate after redirects
                final_url = str(resp.url)
                if final_url != url:
                    validate_public_url(final_url)

                if resp.status_code >= 400:
                    raise AppError(
                        "FETCH_FAILED",
                        f"The page returned {resp.status_code}.",
                        422,
                    )

                content_type = resp.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    raise AppError("NOT_HTML", "The URL did not return an HTML page.", 422)

                body = b""
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    body += chunk
                    if len(body) > _MAX_BYTES:
                        raise AppError("FETCH_FAILED", "Page exceeds the 5 MB size limit.", 422)

    except httpx.TooManyRedirects as exc:
        raise AppError("FETCH_FAILED", "Too many redirects.", 422) from exc
    except httpx.TimeoutException as exc:
        raise AppError("FETCH_FAILED", "Request timed out.", 422) from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError("FETCH_FAILED", f"Could not fetch the page: {exc}", 422) from exc

    html = body.decode("utf-8", errors="replace")

    # Extract main content as markdown (preserves headings)
    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
    )

    if not markdown or len(markdown.strip()) < _MIN_CONTENT_CHARS:
        raise AppError(
            "NO_CONTENT",
            "Could not extract readable text. The page may require JavaScript or a login.",
            422,
        )

    # Derive page title and domain for naming
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    page_title = title_match.group(1).strip() if title_match else urlparse(url).netloc

    sections = _split_by_headings(markdown)

    chunks: list[Chunk] = []
    for heading, body_text in sections:
        if not body_text.strip():
            continue
        locator_heading = heading or page_title
        for piece in split_text(body_text):
            chunks.append(
                Chunk(
                    source_id=source_id,
                    source_type="web",
                    text=piece,
                    locator=Locator(heading=locator_heading),
                )
            )

    if not chunks:
        raise AppError(
            "NO_CONTENT",
            "Could not extract readable text. The page may require JavaScript or a login.",
            422,
        )

    return IngestResult(
        name=page_title,
        source_type="web",
        chunks=chunks,
    )
