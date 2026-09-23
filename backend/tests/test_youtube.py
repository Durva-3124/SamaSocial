"""Tests for YouTube ingestion — all offline via mocks."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.services.ingestion.youtube import (
    group_transcript,
    ingest_youtube,
    parse_video_id,
)

VIDEO_ID = "dQw4w9WgXcQ"


# ---------------------------------------------------------------------------
# parse_video_id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={VIDEO_ID}",
    f"https://youtu.be/{VIDEO_ID}",
    f"https://www.youtube.com/shorts/{VIDEO_ID}",
    f"https://www.youtube.com/embed/{VIDEO_ID}",
    f"https://www.youtube.com/live/{VIDEO_ID}",
    f"https://www.youtube.com/watch?v={VIDEO_ID}&t=30s&list=PL123",
])
def test_parse_video_id_valid(url: str) -> None:
    assert parse_video_id(url) == VIDEO_ID


def test_parse_video_id_invalid() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_video_id("https://example.com/not-a-video")
    assert exc_info.value.code == "INVALID_YOUTUBE_URL"


# ---------------------------------------------------------------------------
# group_transcript
# ---------------------------------------------------------------------------

def _entries(count: int, duration: int = 10) -> list[dict]:
    return [{"text": f"word{i} text", "start": i * duration, "duration": duration} for i in range(count)]


def test_group_transcript_empty() -> None:
    assert group_transcript([]) == []


def test_group_transcript_respects_window() -> None:
    # 12 entries × 10s each = 120s → should produce at least 2 groups with 60s window
    groups = group_transcript(_entries(12, duration=10), window_seconds=60)
    assert len(groups) >= 2


def test_group_transcript_start_seconds_increasing() -> None:
    groups = group_transcript(_entries(20, duration=10), window_seconds=60)
    starts = [g[0] for g in groups]
    assert starts == sorted(starts)


def test_group_transcript_10min_yields_about_10_chunks() -> None:
    # 60 entries × 10s = 600s (10 min), window=60s → ~10 groups
    groups = group_transcript(_entries(60, duration=10), window_seconds=60)
    assert 8 <= len(groups) <= 12


def test_parse_vtt() -> None:
    from app.services.ingestion.youtube import _parse_vtt

    entries = _parse_vtt(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nHello <b>world</b>\n"
    )

    assert entries == [{"text": "Hello world", "start": 1.0, "duration": 2.5}]


def test_blocked_transcript_uses_yt_dlp_fallback() -> None:
    from app.services.ingestion import youtube

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi.list_transcripts", side_effect=RuntimeError("429 Too Many Requests")),
        patch("app.services.ingestion.youtube._fetch_transcript_with_yt_dlp", return_value=[{"text": "fallback", "start": 0, "duration": 1}]),
    ):
        assert youtube._fetch_transcript("dQw4w9WgXcQ") == [
            {"text": "fallback", "start": 0, "duration": 1}
        ]


def test_empty_caption_response_uses_yt_dlp_fallback() -> None:
    from app.services.ingestion import youtube

    transcript = MagicMock()
    transcript.fetch.side_effect = ValueError("no element found: line 1, column 0")
    transcript_list = MagicMock()
    transcript_list.find_manually_created_transcript.return_value = transcript

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi.list_transcripts", return_value=transcript_list),
        patch("app.services.ingestion.youtube._fetch_transcript_with_yt_dlp", return_value=[{"text": "fallback", "start": 0, "duration": 1}]),
    ):
        assert youtube._fetch_transcript("dQw4w9WgXcQ") == [
            {"text": "fallback", "start": 0, "duration": 1}
        ]


# ---------------------------------------------------------------------------
# ingest_youtube (mocked _fetch_transcript and _fetch_title)
# ---------------------------------------------------------------------------

def _fake_entries() -> list[dict]:
    return [{"text": f"sentence {i} about topic", "start": i * 10, "duration": 10} for i in range(30)]


@pytest.mark.asyncio
async def test_ingest_youtube_happy_path() -> None:
    with (
        patch("app.services.ingestion.youtube._fetch_transcript", return_value=_fake_entries()),
        patch("app.services.ingestion.youtube._fetch_title", return_value="Test Video"),
    ):
        result = await ingest_youtube("src1", f"https://youtu.be/{VIDEO_ID}")

    assert result.name == "Test Video"
    assert result.source_type == "youtube"
    assert len(result.chunks) > 0
    # All chunks have start_seconds set
    assert all(c.locator.start_seconds is not None for c in result.chunks)
    # start_seconds are non-decreasing
    starts = [c.locator.start_seconds for c in result.chunks]
    assert starts == sorted(starts)


@pytest.mark.asyncio
async def test_ingest_youtube_title_fallback() -> None:
    with (
        patch("app.services.ingestion.youtube._fetch_transcript", return_value=_fake_entries()),
        patch("app.services.ingestion.youtube._fetch_title", return_value=f"YouTube video {VIDEO_ID}"),
    ):
        result = await ingest_youtube("s", f"https://youtu.be/{VIDEO_ID}")
    assert VIDEO_ID in result.name


@pytest.mark.asyncio
async def test_ingest_youtube_transcript_disabled() -> None:
    with patch(
        "app.services.ingestion.youtube._fetch_transcript",
        side_effect=AppError("TRANSCRIPT_DISABLED", "disabled", 422),
    ):
        with pytest.raises(AppError) as exc_info:
            await ingest_youtube("s", f"https://youtu.be/{VIDEO_ID}")
    assert exc_info.value.code == "TRANSCRIPT_DISABLED"


@pytest.mark.asyncio
async def test_ingest_youtube_video_unavailable() -> None:
    with patch(
        "app.services.ingestion.youtube._fetch_transcript",
        side_effect=AppError("VIDEO_UNAVAILABLE", "unavailable", 422),
    ):
        with pytest.raises(AppError) as exc_info:
            await ingest_youtube("s", f"https://youtu.be/{VIDEO_ID}")
    assert exc_info.value.code == "VIDEO_UNAVAILABLE"


@pytest.mark.asyncio
async def test_ingest_youtube_blocked() -> None:
    with patch(
        "app.services.ingestion.youtube._fetch_transcript",
        side_effect=AppError("YOUTUBE_BLOCKED", "blocked", 502),
    ):
        with pytest.raises(AppError) as exc_info:
            await ingest_youtube("s", f"https://youtu.be/{VIDEO_ID}")
    assert exc_info.value.code == "YOUTUBE_BLOCKED"


@pytest.mark.asyncio
async def test_ingest_youtube_invalid_url() -> None:
    with pytest.raises(AppError) as exc_info:
        await ingest_youtube("s", "https://example.com/not-youtube")
    assert exc_info.value.code == "INVALID_YOUTUBE_URL"
