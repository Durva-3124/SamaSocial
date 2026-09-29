"""Tests for SSRF URL safety validation — covers classification, SSRF, redirects, spoofing."""
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError
from app.core.url_safety import (
    classify_url,
    extract_youtube_video_id,
    follow_safe_redirects,
    validate_ingest_url,
    validate_public_url,
    YOUTUBE_HOSTS,
    YOUTUBE_SHORT_HOSTS,
)


def _mock_dns(ip: str):
    """Return a patch that makes getaddrinfo resolve to the given IP."""
    return patch(
        "app.core.url_safety.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 80))],
    )


# ---------------------------------------------------------------------------
# Scheme validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ftp://example.com",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,<h1>x</h1>",
])
def test_rejects_unsupported_url_schemes(url: str) -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url(url)
    assert exc_info.value.code == "UNSAFE_URL"


def test_allows_http_scheme() -> None:
    with _mock_dns("93.184.216.34"):
        result = validate_public_url("http://example.com/page")
    assert result.startswith("http://")


def test_allows_https_scheme() -> None:
    with _mock_dns("8.8.8.8"):
        result = validate_public_url("https://dns.google/")
    assert result.startswith("https://")


# ---------------------------------------------------------------------------
# Forbidden character / credential / structure checks
# ---------------------------------------------------------------------------

def test_rejects_backslash_in_url() -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url("https://youtube.com\\@evil.com/watch?v=dQw4w9WgXcQ")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_url_with_credentials() -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url("https://user:pass@example.com/page")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_null_byte_in_url() -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url("https://example.com/pa\x00th")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_empty_url() -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url("")
    assert exc_info.value.code == "UNSAFE_URL"


# ---------------------------------------------------------------------------
# SSRF — blocked destinations
# ---------------------------------------------------------------------------

def test_rejects_loopback_127() -> None:
    with _mock_dns("127.0.0.1"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://example.com/path")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_loopback_literal_ip() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_ingest_url("https://127.0.0.1/admin")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_localhost() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_public_url("http://localhost/admin")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_private_10x() -> None:
    with _mock_dns("10.0.0.1"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://internal.corp/secret")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_private_192_168() -> None:
    with _mock_dns("192.168.1.1"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://router.local/")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_private_172_16() -> None:
    with _mock_dns("172.16.0.1"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://internal.example.com/")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_link_local_169_254() -> None:
    with _mock_dns("169.254.169.254"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://metadata.aws/latest/")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_ipv4_mapped_loopback() -> None:
    """::ffff:127.0.0.1 must be blocked via IPv4-mapped check."""
    with pytest.raises(AppError) as exc_info:
        validate_ingest_url("https://[::ffff:127.0.0.1]/")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_ftp_scheme() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_public_url("ftp://example.com/file.txt")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_unresolvable_host() -> None:
    with patch(
        "app.core.url_safety.socket.getaddrinfo",
        side_effect=socket.gaierror("Name not resolved"),
    ):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://this-does-not-exist.invalid/")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_metadata_google_internal() -> None:
    """metadata.google.internal is a blocked hostname regardless of resolution."""
    with pytest.raises(AppError) as exc_info:
        classify_url("http://metadata.google.internal/computeMetadata/v1/")
    assert exc_info.value.code == "UNSAFE_URL"


def test_rejects_dotlocal_suffix() -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url("http://printer.local/status")
    assert exc_info.value.code == "UNSAFE_URL"


# ---------------------------------------------------------------------------
# SSRF — allowed destinations
# ---------------------------------------------------------------------------

def test_allows_public_ip() -> None:
    with _mock_dns("93.184.216.34"):  # example.com
        result = validate_public_url("https://example.com/page")
    assert result == "https://example.com/page"


def test_allows_https() -> None:
    with _mock_dns("8.8.8.8"):
        result = validate_public_url("https://dns.google/")
    assert result.startswith("https://")


def test_allows_bare_domain_without_scheme() -> None:
    """A bare hostname without scheme is accepted with https:// prepended."""
    parsed = classify_url("example.com")
    assert parsed.scheme == "https"
    assert parsed.hostname == "example.com"


# ---------------------------------------------------------------------------
# YouTube classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/e/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Watch URL with extra params
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s&list=PL123", "dQw4w9WgXcQ"),
        # Bare /watch path (no path segment, just query)
        ("https://youtube.com/?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_classifies_supported_youtube_hosts(url: str, video_id: str) -> None:
    parsed = classify_url(url)
    assert parsed.kind == "youtube", f"Expected youtube for {url!r}"
    assert parsed.video_id == video_id, f"Expected {video_id!r} for {url!r}"
    assert parsed.is_youtube is True


@pytest.mark.parametrize(
    "url",
    [
        # Host-based spoofing
        "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be.evil.com/dQw4w9WgXcQ",
        "https://www.youtube.com.phish.io/watch?v=dQw4w9WgXcQ",
        # Path-based spoofing (YouTube-looking path on a foreign host)
        "https://evil.com/youtu.be/dQw4w9WgXcQ",
        "https://evil.com/youtube.com/watch?v=dQw4w9WgXcQ",
        # Subdomain spoofing
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_spoofed_youtube_urls_remain_web(url: str) -> None:
    parsed = classify_url(url)
    assert parsed.kind == "web", f"Expected 'web' for spoofed URL {url!r}"
    assert parsed.video_id is None


# ---------------------------------------------------------------------------
# extract_youtube_video_id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("hostname", "path", "query", "expected_id"),
    [
        # Short link
        ("youtu.be", "/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        ("www.youtu.be", "/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        # Classic watch
        ("youtube.com", "/watch", "v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("www.youtube.com", "/watch", "v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Path prefixes
        ("youtube.com", "/shorts/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        ("youtube.com", "/embed/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        ("youtube.com", "/e/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        ("youtube.com", "/live/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        ("youtube.com", "/v/dQw4w9WgXcQ", "", "dQw4w9WgXcQ"),
        # Bare path (just query)
        ("youtube.com", "/", "v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("youtube.com", "", "v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # No id → None
        ("youtube.com", "/channel/UCxxxxxxxx", "", None),
        ("youtube.com", "/watch", "", None),
        ("youtu.be", "/", "", None),
        # Invalid id length
        ("youtu.be", "/tooshort", "", None),
        ("youtube.com", "/shorts/toolongtobeanid_overeleven", "", None),
    ],
)
def test_extract_youtube_video_id(hostname, path, query, expected_id) -> None:
    result = extract_youtube_video_id(hostname, path, query)
    assert result == expected_id, f"hostname={hostname!r} path={path!r} query={query!r}"


def test_extract_youtube_video_id_ignores_non_youtube_hosts() -> None:
    """The extractor must return None for arbitrary hosts even with matching paths."""
    result = extract_youtube_video_id("evil.com", "/watch", "v=dQw4w9WgXcQ")
    assert result is None


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------

def test_normalised_url_strips_fragment() -> None:
    parsed = classify_url("https://example.com/page#section")
    assert "#" not in parsed.normalized


def test_normalised_url_lowercases_host() -> None:
    parsed = classify_url("https://EXAMPLE.COM/Page")
    assert parsed.hostname == "example.com"


def test_fqdn_trailing_dot_normalised() -> None:
    """youtube.com. (with trailing FQDN dot) must classify as YouTube, not web."""
    parsed = classify_url("https://youtube.com./watch?v=dQw4w9WgXcQ")
    assert parsed.kind == "youtube"
    assert parsed.video_id == "dQw4w9WgXcQ"


# ---------------------------------------------------------------------------
# Redirect safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redirect_to_private_address_is_rejected_before_request() -> None:
    response = MagicMock(is_redirect=True, headers={"location": "http://127.0.0.1/admin"})
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    with _mock_dns("93.184.216.34"), pytest.raises(AppError) as exc_info:
        await follow_safe_redirects(client, "https://example.com/start")

    assert exc_info.value.code == "UNSAFE_URL"
    # Only one GET must have been made (to the first URL, not the redirect target)
    assert client.get.await_count == 1


@pytest.mark.asyncio
async def test_follows_valid_redirect() -> None:
    redirect = MagicMock(is_redirect=True, headers={"location": "/article"})
    final = MagicMock(is_redirect=False, headers={})
    client = MagicMock()
    client.get = AsyncMock(side_effect=[redirect, final])

    with _mock_dns("93.184.216.34"):
        response, final_url = await follow_safe_redirects(client, "https://example.com/start")

    assert response is final
    assert final_url == "https://example.com/article"
    assert [call.args[0] for call in client.get.await_args_list] == [
        "https://example.com/start",
        "https://example.com/article",
    ]


@pytest.mark.asyncio
async def test_redirect_chain_too_long_raises_fetch_failed() -> None:
    # Always redirect — will hit the max_redirects cap
    redirect = MagicMock(is_redirect=True, headers={"location": "https://example.com/next"})
    client = MagicMock()
    client.get = AsyncMock(return_value=redirect)

    with _mock_dns("93.184.216.34"), pytest.raises(AppError) as exc_info:
        await follow_safe_redirects(client, "https://example.com/start", max_redirects=3)

    assert exc_info.value.code == "FETCH_FAILED"
    assert "redirect" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_redirect_with_no_location_header_stops() -> None:
    """A redirect response with no Location header should stop and return the response."""
    redirect = MagicMock(is_redirect=True, headers={})
    client = MagicMock()
    client.get = AsyncMock(return_value=redirect)

    with _mock_dns("93.184.216.34"):
        response, final_url = await follow_safe_redirects(client, "https://example.com/start")

    assert response is redirect
    assert final_url == "https://example.com/start"
    assert client.get.await_count == 1
