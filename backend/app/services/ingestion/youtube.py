"""YouTube transcript ingestion with timestamped chunks."""
import asyncio
import logging
import re
from xml.etree.ElementTree import ParseError
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.errors import AppError
from app.core.config import get_settings
from app.models.chunk import Chunk, Locator
from app.services.chunking import split_text
from app.services.ingestion.base import IngestResult

logger = logging.getLogger(__name__)

_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_VTT_TIMESTAMP_RE = re.compile(
    r"(?P<hours>\d{2}:)?(?P<minutes>\d{2}):(?P<seconds>\d{2})[.,](?P<millis>\d{3})"
)


def parse_video_id(url: str) -> str:
    """Extract the 11-char video ID from any YouTube URL format."""
    # Try regex first (handles most cases)
    m = _YT_ID_RE.search(url)
    if m:
        return m.group(1)
    # Fallback: parse query string
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
    raise AppError("INVALID_YOUTUBE_URL", f"Could not extract a video ID from: {url}", 422)


def _parse_vtt_timestamp(value: str) -> float:
    match = _VTT_TIMESTAMP_RE.search(value)
    if not match:
        return 0.0
    hours = int((match.group("hours") or "00:")[:-1])
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int(match.group("millis"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _parse_vtt(content: str) -> list[dict]:
    """Convert a WebVTT caption track into the common transcript shape."""
    entries: list[dict] = []
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n"))
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        timing = lines[timing_index].split("-->", 1)
        if len(timing) != 2:
            continue
        text = re.sub(r"<[^>]+>", "", " ".join(lines[timing_index + 1:])).strip()
        if text:
            start = _parse_vtt_timestamp(timing[0])
            end = _parse_vtt_timestamp(timing[1])
            entries.append({"text": text, "start": start, "duration": max(0.0, end - start)})
    return entries


def _fetch_transcript_with_yt_dlp(video_id: str) -> list[dict]:
    """Fallback caption fetcher for servers rate-limited by YouTube HTML."""
    try:
        import yt_dlp  # type: ignore[import-untyped]

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignore_no_formats_error": True,
        }
        proxy = get_settings().YOUTUBE_PROXY
        if proxy:
            options["proxy"] = proxy
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            tracks = info.get("subtitles", {}) or {}
            for language, captions in (info.get("automatic_captions", {}) or {}).items():
                tracks.setdefault(language, captions)
            selected = next(
                (tracks[language] for language in ("en", "en-US", "en-GB") if language in tracks),
                next(iter(tracks.values()), []),
            )
            track = next((item for item in selected if item.get("ext") == "vtt"), None)
            if track is None and selected:
                track = selected[0]
            if not track or not track.get("url"):
                return []
            response = ydl.urlopen(track["url"])
            return _parse_vtt(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("yt-dlp transcript fallback failed for %s: %s", video_id, exc)
        return []


def _fetch_transcript(video_id: str) -> list[dict]:
    """Fetch transcript entries [{text, start, duration}] for a video.

    This is the ONLY function that touches youtube-transcript-api.
    """
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-untyped]
    from youtube_transcript_api._errors import (  # type: ignore[import-untyped]
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )

    try:
        proxy = get_settings().YOUTUBE_PROXY
        transcript_list = YouTubeTranscriptApi.list_transcripts(
            video_id,
            proxies={"http": proxy, "https": proxy} if proxy else None,
        )
    except TranscriptsDisabled:
        raise AppError("TRANSCRIPT_DISABLED", "Transcripts are disabled for this video.", 422)
    except VideoUnavailable:
        raise AppError("VIDEO_UNAVAILABLE", "This video is unavailable.", 422)
    except Exception as exc:
        msg = str(exc).lower()
        if "blocked" in msg or "ip" in msg or "429" in msg:
            fallback = _fetch_transcript_with_yt_dlp(video_id)
            if fallback:
                logger.info("Used yt-dlp caption fallback for YouTube video %s", video_id)
                return fallback
            raise AppError(
                "YOUTUBE_BLOCKED",
                "YouTube is rate-limiting this server. Set YOUTUBE_PROXY to a proxy with YouTube access, or run the backend from another network.",
                502,
            )
        raise AppError("TRANSCRIPT_DISABLED", f"Could not fetch transcript: {exc}", 422) from exc

    # Prefer manually created English, then auto-generated English, then any
    transcript = None
    try:
        transcript = transcript_list.find_manually_created_transcript(["en"])
    except NoTranscriptFound:
        pass
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(["en"])
        except NoTranscriptFound:
            pass
    if transcript is None:
        try:
            transcript = transcript_list.find_transcript(
                [t.language_code for t in transcript_list]
            )
        except NoTranscriptFound:
            raise AppError("TRANSCRIPT_DISABLED", "No transcript available for this video.", 422)

    try:
        return transcript.fetch()
    except Exception as exc:
        fallback = _fetch_transcript_with_yt_dlp(video_id)
        if fallback:
            logger.info("Used yt-dlp caption fallback for YouTube video %s", video_id)
            return fallback
        if isinstance(exc, ParseError) or not str(exc).strip():
            raise AppError(
                "YOUTUBE_BLOCKED",
                "YouTube returned an empty caption response. Set YOUTUBE_PROXY to a proxy with YouTube access, or run the backend from another network.",
                502,
            ) from exc
        raise AppError("TRANSCRIPT_DISABLED", f"Could not fetch transcript: {exc}", 422) from exc


def _fetch_title(url: str, video_id: str) -> str:
    """Fetch video title via oEmbed; falls back to a generic name."""
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("title", f"YouTube video {video_id}")
    except Exception:
        pass
    return f"YouTube video {video_id}"


def group_transcript(
    entries: list[dict],
    window_seconds: int = 60,
    max_words: int = 200,
) -> list[tuple[int, str]]:
    """Merge transcript entries into windows of ~window_seconds seconds.

    Returns list of (start_second, text) tuples.
    """
    if not entries:
        return []

    groups: list[tuple[int, str]] = []
    window_start = int(entries[0].get("start", 0))
    window_texts: list[str] = []
    window_words = 0

    for entry in entries:
        start = int(entry.get("start", 0))
        text = entry.get("text", "").strip()
        words = len(text.split())

        time_exceeded = (start - window_start) >= window_seconds
        words_exceeded = window_words + words > max_words

        if (time_exceeded or words_exceeded) and window_texts:
            groups.append((window_start, " ".join(window_texts)))
            window_start = start
            window_texts = []
            window_words = 0

        window_texts.append(text)
        window_words += words

    if window_texts:
        groups.append((window_start, " ".join(window_texts)))

    return groups


async def ingest_youtube(source_id: str, url: str) -> IngestResult:
    """Ingest a YouTube video transcript into timestamped chunks."""
    video_id = parse_video_id(url)

    # Blocking calls run in threads
    entries = await asyncio.to_thread(_fetch_transcript, video_id)
    title = await asyncio.to_thread(_fetch_title, url, video_id)

    groups = group_transcript(entries)

    chunks: list[Chunk] = []
    for start_sec, text in groups:
        for piece in split_text(text):
            chunks.append(
                Chunk(
                    source_id=source_id,
                    source_type="youtube",
                    text=piece,
                    locator=Locator(start_seconds=start_sec),
                )
            )

    if not chunks:
        raise AppError("TRANSCRIPT_DISABLED", "No usable transcript content found.", 422)

    return IngestResult(
        name=title,
        source_type="youtube",
        chunks=chunks,
    )
