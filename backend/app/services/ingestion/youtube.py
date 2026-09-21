"""YouTube transcript ingestion with timestamped chunks."""
import asyncio
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.errors import AppError
from app.models.chunk import Chunk, Locator
from app.services.chunking import split_text
from app.services.ingestion.base import IngestResult

logger = logging.getLogger(__name__)

_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
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
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except TranscriptsDisabled:
        raise AppError("TRANSCRIPT_DISABLED", "Transcripts are disabled for this video.", 422)
    except VideoUnavailable:
        raise AppError("VIDEO_UNAVAILABLE", "This video is unavailable.", 422)
    except Exception as exc:
        msg = str(exc).lower()
        if "blocked" in msg or "ip" in msg or "429" in msg:
            raise AppError(
                "YOUTUBE_BLOCKED",
                "YouTube blocked the transcript request from this server. Try another video or run locally.",
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

    return transcript.fetch()


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
