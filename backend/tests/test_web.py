"""Tests for webpage ingestion — httpx patched with unittest.mock."""
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError
from app.services.ingestion.web import ingest_web

# A minimal HTML page with headings and enough content to pass extraction
_GOOD_HTML = b"""<!DOCTYPE html>
<html><head><title>Test Page</title></head>
<body>
<h1>Introduction</h1>
<p>This is the introduction section with plenty of readable text about a topic.
It contains multiple sentences to ensure trafilatura can extract meaningful content.
The quick brown fox jumps over the lazy dog. Learning is a lifelong journey.</p>
<h2>Details</h2>
<p>Here are the details of the subject matter. This section elaborates on the
introduction with more specific information. Data science involves statistics,
programming, and domain expertise working together to extract insights.</p>
<h2>Conclusion</h2>
<p>In conclusion, this page demonstrates heading-based chunking for web ingestion.
The system splits content by headings and creates separate chunks for each section.
This improves retrieval precision by keeping related content together.</p>
</body></html>"""

_PUBLIC_IP = "93.184.216.34"


def _mock_dns():
    return patch(
        "app.core.url_safety.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (_PUBLIC_IP, 80))],
    )


def _make_stream_client(status: int, content: bytes, content_type: str = "text/html"):
    """Build a mock httpx async streaming client."""
    resp = MagicMock()
    resp.status_code = status
    resp.url = "https://example.com/page"
    resp.headers = {"content-type": content_type}

    async def _aiter_bytes(chunk_size=8192):
        yield content

    resp.aiter_bytes = _aiter_bytes

    stream_cm = AsyncMock()
    stream_cm.__aenter__ = AsyncMock(return_value=resp)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client = AsyncMock()
    client.stream = MagicMock(return_value=stream_cm)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_headings_become_locators() -> None:
    with _mock_dns(), patch("app.services.ingestion.web.httpx.AsyncClient", return_value=_make_stream_client(200, _GOOD_HTML)):
        result = await ingest_web("s1", "https://example.com/page")

    assert result.source_type == "web"
    assert len(result.chunks) > 0
    headings = {c.locator.heading for c in result.chunks}
    # At least one heading should be present
    assert any(h for h in headings)


@pytest.mark.asyncio
async def test_page_title_used_as_name() -> None:
    with _mock_dns(), patch("app.services.ingestion.web.httpx.AsyncClient", return_value=_make_stream_client(200, _GOOD_HTML)):
        result = await ingest_web("s1", "https://example.com/page")
    assert result.name == "Test Page"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_html_content_type_rejected() -> None:
    with _mock_dns(), patch(
        "app.services.ingestion.web.httpx.AsyncClient",
        return_value=_make_stream_client(200, b"data", content_type="application/pdf"),
    ):
        with pytest.raises(AppError) as exc_info:
            await ingest_web("s", "https://example.com/file.pdf")
    assert exc_info.value.code == "NOT_HTML"


@pytest.mark.asyncio
async def test_404_raises_fetch_failed() -> None:
    with _mock_dns(), patch(
        "app.services.ingestion.web.httpx.AsyncClient",
        return_value=_make_stream_client(404, b"Not Found"),
    ):
        with pytest.raises(AppError) as exc_info:
            await ingest_web("s", "https://example.com/missing")
    assert exc_info.value.code == "FETCH_FAILED"
    assert "404" in exc_info.value.message


@pytest.mark.asyncio
async def test_oversized_body_raises_fetch_failed() -> None:
    big = b"x" * (6 * 1024 * 1024)  # 6 MB

    resp = MagicMock()
    resp.status_code = 200
    resp.url = "https://example.com/page"
    resp.headers = {"content-type": "text/html"}

    async def _aiter_bytes(chunk_size=8192):
        # yield in 1 MB chunks
        for i in range(0, len(big), 1024 * 1024):
            yield big[i : i + 1024 * 1024]

    resp.aiter_bytes = _aiter_bytes
    stream_cm = AsyncMock()
    stream_cm.__aenter__ = AsyncMock(return_value=resp)
    stream_cm.__aexit__ = AsyncMock(return_value=False)
    client = AsyncMock()
    client.stream = MagicMock(return_value=stream_cm)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with _mock_dns(), patch("app.services.ingestion.web.httpx.AsyncClient", return_value=client):
        with pytest.raises(AppError) as exc_info:
            await ingest_web("s", "https://example.com/big")
    assert exc_info.value.code == "FETCH_FAILED"


@pytest.mark.asyncio
async def test_js_only_page_raises_no_content() -> None:
    js_html = b"<html><body><div id='app'></div><script>app.init()</script></body></html>"
    with _mock_dns(), patch(
        "app.services.ingestion.web.httpx.AsyncClient",
        return_value=_make_stream_client(200, js_html),
    ):
        with pytest.raises(AppError) as exc_info:
            await ingest_web("s", "https://example.com/spa")
    assert exc_info.value.code == "NO_CONTENT"


@pytest.mark.asyncio
async def test_unsafe_url_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        await ingest_web("s", "http://localhost/admin")
    assert exc_info.value.code == "UNSAFE_URL"
