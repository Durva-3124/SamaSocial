"""Tests for SSRF URL safety validation."""
import socket
from unittest.mock import patch

import pytest

from app.core.errors import AppError
from app.core.url_safety import classify_url, follow_safe_redirects, validate_public_url


def _mock_dns(ip: str):
    """Return a patch that makes getaddrinfo resolve to the given IP."""
    return patch(
        "app.core.url_safety.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 80))],
    )


# ---------------------------------------------------------------------------
# Blocked cases
# ---------------------------------------------------------------------------

def test_rejects_loopback_127() -> None:
    with _mock_dns("127.0.0.1"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://example.com/path")
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


def test_rejects_link_local_169_254() -> None:
    with _mock_dns("169.254.169.254"):
        with pytest.raises(AppError) as exc_info:
            validate_public_url("http://metadata.aws/latest/")
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


# ---------------------------------------------------------------------------
# Allowed cases
# ---------------------------------------------------------------------------

def test_allows_public_ip() -> None:
    with _mock_dns("93.184.216.34"):  # example.com
        result = validate_public_url("https://example.com/page")
    assert result == "https://example.com/page"


def test_allows_https() -> None:
    with _mock_dns("8.8.8.8"):
        result = validate_public_url("https://dns.google/")
    assert result.startswith("https://")


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_classifies_supported_youtube_hosts(url: str, video_id: str) -> None:
    parsed = classify_url(url)
    assert parsed.kind == "youtube"
    assert parsed.video_id == video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be.evil.com/dQw4w9WgXcQ",
        "https://evil.com/youtu.be/dQw4w9WgXcQ",
    ],
)
def test_spoofed_youtube_urls_remain_web(url: str) -> None:
    assert classify_url(url).kind == "web"


@pytest.mark.parametrize("url", ["ftp://example.com", "file:///etc/passwd", "javascript:alert(1)"])
def test_rejects_unsupported_url_schemes(url: str) -> None:
    with pytest.raises(AppError) as exc_info:
        classify_url(url)
    assert exc_info.value.code == "UNSAFE_URL"


@pytest.mark.asyncio
async def test_redirect_to_private_address_is_rejected_before_request() -> None:
    from unittest.mock import AsyncMock, MagicMock

    response = MagicMock(is_redirect=True, headers={"location": "http://127.0.0.1/admin"})
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    with _mock_dns("93.184.216.34"), pytest.raises(AppError) as exc_info:
        await follow_safe_redirects(client, "https://example.com/start")

    assert exc_info.value.code == "UNSAFE_URL"
    assert client.get.await_count == 1


@pytest.mark.asyncio
async def test_follows_valid_redirect() -> None:
    from unittest.mock import AsyncMock, MagicMock

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
