"""Tests for SSRF URL safety validation."""
import socket
from unittest.mock import patch

import pytest

from app.core.errors import AppError
from app.core.url_safety import validate_public_url


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
