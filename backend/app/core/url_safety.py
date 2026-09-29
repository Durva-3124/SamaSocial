"""Authoritative URL classification and SSRF safety for source ingestion.

This module is the **single source of truth** for every URL decision made by
the Learning Assistant source pipeline:

* which schemes are accepted,
* how a raw string becomes a normalised URL,
* how a hostname is normalised and compared,
* whether a URL is a YouTube video URL (and its video id),
* whether a URL resolves to a public, non-private address,
* how redirects are followed so every hop is validated *before* it is fetched.

No other module may re-implement any of these checks. The API layer
(``app.api.sessions``) and the ingest manager (``app.services.ingest_manager``)
both call in here, which is what makes the pipeline consistent end to end.

Design notes
------------
* Host matching is **exact set membership**, never substring or suffix
  matching. This is what rejects ``youtube.com.evil.com``,
  ``youtu.be.evil.com``, ``notyoutube.com`` and ``evil.com/youtu.be/x``.
* Backslashes and control characters are rejected outright. ``urlparse`` and
  httpx/browsers disagree about how to treat ``\\`` in a URL, and that
  disagreement is exploitable: ``https://evil.com\\@youtube.com/watch?v=x``
  parses to hostname ``youtube.com`` but is fetched from ``evil.com``.
* Redirects are followed manually, one hop at a time, with full validation of
  each new target *before* a request is issued to it.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from app.core.errors import AppError

__all__ = [
    "ALLOWED_SCHEMES",
    "ParsedUrl",
    "UrlKind",
    "classify_url",
    "extract_youtube_video_id",
    "follow_safe_redirects",
    "validate_ingest_url",
    "validate_public_url",
]

# ── Policy constants ──────────────────────────────────────────────────────────

#: The only schemes a source URL may use. ``file:``, ``ftp:``, ``javascript:``
#: and ``data:`` are all rejected.
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

#: YouTube hostnames that are matched **exactly** after normalisation.
YOUTUBE_HOSTS: frozenset[str] = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)

#: youtu.be is a separate short-link domain with its own path grammar.
YOUTUBE_SHORT_HOSTS: frozenset[str] = frozenset({"youtu.be", "www.youtu.be"})

#: Hostnames that must never be fetched, regardless of what they resolve to.
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)

#: Hostname suffixes that are internal-by-convention (mDNS / split-horizon DNS).
_BLOCKED_SUFFIXES: tuple[str, ...] = (".localhost", ".local", ".internal", ".home.arpa")

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
# Characters that either control output or create a parser differential between
# urllib and the HTTP client. All of them are refused.
_FORBIDDEN_CHARS_RE = re.compile(r"[\x00-\x20\x7f\\]")

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: YouTube path prefixes that carry the video id as the next path segment.
_YOUTUBE_PATH_PREFIXES: tuple[str, ...] = ("shorts", "embed", "live", "v")

_UNSAFE_MESSAGE = "That URL is not allowed."

UrlKind = Literal["youtube", "web"]


def _unsafe(message: str = _UNSAFE_MESSAGE) -> AppError:
    return AppError("UNSAFE_URL", message, 422)


def _normalise_hostname(raw: str) -> str:
    """Lowercase, strip IPv6 brackets and drop the FQDN trailing dot.

    ``youtube.com.`` and ``youtube.com`` are the same DNS name, so they must
    normalise to the same value or the exact-match YouTube check can be
    sidestepped.
    """
    host = raw.strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host.rstrip(".")


# ── Parsing / classification ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedUrl:
    """A validated, normalised URL plus its ingestion classification."""

    original: str
    """The caller's original string, unchanged (for user-facing messages)."""

    normalized: str
    """The canonical URL string that should actually be fetched."""

    scheme: str
    hostname: str
    port: int | None
    path: str
    query: str
    fragment: str
    kind: UrlKind
    """``"youtube"`` for YouTube URLs, ``"web"`` for everything else."""

    video_id: str | None
    """The 11-character YouTube id, when ``kind == "youtube"``."""

    @property
    def is_youtube(self) -> bool:
        return self.kind == "youtube"


def classify_url(url: str, *, allow_scheme_less: bool = True) -> ParsedUrl:
    """Parse, normalise and classify a URL without touching the network.

    Performs scheme, character, credential and hostname checks. Hostnames are
    *not* resolved here — use :func:`validate_public_url` or
    :func:`validate_ingest_url` for that.

    Raises:
        AppError: ``UNSAFE_URL`` (422) for any malformed, non-HTTP(S) or
            otherwise unacceptable URL.
    """
    if not isinstance(url, str):
        raise _unsafe()

    candidate = url.strip()
    if not candidate:
        raise _unsafe()

    # Reject control characters and backslashes *before* parsing. urllib and
    # httpx disagree on backslash handling, and that gap is a live bypass.
    if _FORBIDDEN_CHARS_RE.search(candidate):
        raise _unsafe()

    # A bare host like "example.com" has no scheme. Give it https:// rather
    # than failing, but only when it genuinely has no scheme token at all --
    # "localhost:8000" parses as scheme "localhost" and must be rejected.
    if allow_scheme_less and _SCHEME_RE.match(candidate) is None:
        candidate = f"https://{candidate}"

    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError as exc:  # malformed port, bad IPv6 literal, etc.
        raise _unsafe() from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise _unsafe()

    if not parsed.netloc:
        raise _unsafe()

    # Credentials are never needed for public ingestion and enable
    # "https://trusted.com@evil.com" style confusion. Refuse them.
    if parsed.username is not None or parsed.password is not None:
        raise _unsafe()

    if not parsed.hostname:
        raise _unsafe()

    hostname = _normalise_hostname(parsed.hostname)
    if not hostname:
        raise _unsafe()

    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(_BLOCKED_SUFFIXES):
        raise _unsafe()

    if port is not None and not (1 <= port <= 65535):
        raise _unsafe()

    normalized = urlunparse(
        (scheme, parsed.netloc.lower(), parsed.path or "/", parsed.params, parsed.query, "")
    )

    if hostname in YOUTUBE_HOSTS:
        kind: UrlKind = "youtube"
    elif hostname in YOUTUBE_SHORT_HOSTS:
        kind = "youtube"
    else:
        kind = "web"

    return ParsedUrl(
        original=url,
        normalized=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        path=parsed.path,
        query=parsed.query,
        fragment=parsed.fragment,
        kind=kind,
        video_id=extract_youtube_video_id(hostname, parsed.path, parsed.query),
    )


def extract_youtube_video_id(hostname: str, path: str, query: str) -> str | None:
    """Extract an 11-character YouTube video id from *host-scoped* components.

    The hostname, path and query must be supplied separately so that the id can
    never be lifted out of some unrelated domain. ``extract_youtube_video_id`` is
    only called with a hostname already known to be a YouTube host.

    Returns ``None`` when no well-formed id is present.
    """
    host = _normalise_hostname(hostname)
    segments = [segment for segment in (path or "").split("/") if segment]

    if host in YOUTUBE_SHORT_HOSTS:
        candidate = segments[0] if segments else None
        return candidate if candidate and _VIDEO_ID_RE.match(candidate) else None

    if host in YOUTUBE_HOSTS:
        if segments and segments[0] in _YOUTUBE_PATH_PREFIXES and len(segments) > 1:
            candidate = segments[1]
            return candidate if _VIDEO_ID_RE.match(candidate) else None
        if segments[:1] == ["watch"]:
            values = parse_qs(query or "").get("v")
            if values and _VIDEO_ID_RE.match(values[0]):
                return values[0]

    return None


# ── Network safety ────────────────────────────────────────────────────────────


def _assert_public_address(raw_ip: str) -> None:
    """Reject loopback, private, link-local, multicast, reserved and mapped addresses."""
    try:
        ip = ipaddress.ip_address(raw_ip)
    except ValueError:
        return

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise _unsafe()

    # IPv4-mapped / IPv4-compatible IPv6 (e.g. ::ffff:127.0.0.1) must be judged
    # on the address they actually reach, not on their IPv6 classification.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        _assert_public_address(str(mapped))
        return

    sixtofour = getattr(ip, "sixtofour", None)
    if sixtofour is not None:
        _assert_public_address(str(sixtofour))


def validate_public_url(url: str) -> str:
    """Validate a URL end to end and return its normalised form.

    Applies :func:`classify_url` (scheme, characters, credentials, hostname) and
    then resolves the hostname, refusing any address that is loopback, private,
    link-local, multicast, reserved, unspecified or IPv4-mapped to one of those.

    Raises:
        AppError: ``UNSAFE_URL`` (422) when the URL is not safe to fetch.
    """
    return validate_ingest_url(url).normalized


def validate_ingest_url(url: str) -> ParsedUrl:
    """Full safety check for a URL arriving from a user. Returns the ParsedUrl.

    This is the function the API layer and the ingest manager should call.
    """
    parsed = classify_url(url)

    # A bare IP literal needs no resolution step.
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        _assert_public_address(parsed.hostname)
        return parsed

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or None)
    except socket.gaierror as exc:
        raise _unsafe() from exc

    if not infos:
        raise _unsafe()

    for info in infos:
        try:
            raw_ip = info[4][0]
        except (IndexError, TypeError) as exc:  # pragma: no cover - defensive
            raise _unsafe() from exc
        _assert_public_address(raw_ip)

    return parsed


# ── Safe redirect handling ────────────────────────────────────────────────────

MAX_REDIRECTS = 3


async def follow_safe_redirects(
    client,
    url: str,
    *,
    max_redirects: int = MAX_REDIRECTS,
) -> tuple[object, str]:
    """GET a URL, following redirects manually and validating every hop first.

    ``client`` must be an ``httpx.AsyncClient`` configured with
    ``follow_redirects=False``. Each hop is fully validated with
    :func:`validate_ingest_url` *before* a request is issued to it, so a
    redirect can never be used to reach a private address.

    httpx's own ``follow_redirects`` cannot be used for this: it resolves and
    connects to each redirect target before the caller can inspect it, so the
    post-hoc ``resp.url`` check that older code relied on validated a connection
    that had already been made.

    Returns:
        ``(response, final_url)`` — the last non-redirect response and the URL it
        came from.

    Raises:
        AppError: ``UNSAFE_URL`` for a hop that fails validation,
            ``FETCH_FAILED`` when the redirect chain is too long.
    """
    current = validate_ingest_url(url).normalized

    for _ in range(max_redirects + 1):
        response = await client.get(current)
        if not response.is_redirect:
            return response, current

        location = response.headers.get("location")
        if not location:
            return response, current

        # urljoin resolves a relative Location header against the current URL;
        # the resolved target is then re-validated before we connect to it.
        current = validate_ingest_url(urljoin(current, location)).normalized

    raise AppError("FETCH_FAILED", "Too many redirects.", 422)
