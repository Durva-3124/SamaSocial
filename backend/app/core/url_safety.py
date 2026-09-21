"""URL safety validation — blocks SSRF attempts."""
import ipaddress
import socket

from app.core.errors import AppError


def validate_public_url(url: str) -> str:
    """Validate that a URL is safe to fetch (public, http/https only).

    Raises AppError(UNSAFE_URL) for loopback, private, link-local,
    multicast, reserved IPs, localhost, or non-http(s) schemes.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise AppError("UNSAFE_URL", "That URL is not allowed.", 422)

    hostname = parsed.hostname
    if not hostname:
        raise AppError("UNSAFE_URL", "That URL is not allowed.", 422)

    if hostname.lower() == "localhost":
        raise AppError("UNSAFE_URL", "That URL is not allowed.", 422)

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise AppError("UNSAFE_URL", "That URL is not allowed.", 422) from exc

    for info in infos:
        raw_ip = info[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise AppError("UNSAFE_URL", "That URL is not allowed.", 422)

    return url
