"""Tests for chunking and Chunk.locator_text."""
import pytest

from app.models.chunk import Chunk, Locator
from app.services.chunking import split_text


# ---------------------------------------------------------------------------
# split_text
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty() -> None:
    assert split_text("") == []
    assert split_text("   ") == []


def test_short_text_single_chunk() -> None:
    result = split_text("Hello world. This is a test.")
    assert len(result) == 1
    assert "Hello" in result[0]


def test_max_words_respected() -> None:
    # 400 words, max=350 → must produce at least 2 chunks
    words = " ".join(f"word{i}" for i in range(400))
    chunks = split_text(words, max_words=350, overlap_words=0)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.split()) <= 350


def test_overlap_present() -> None:
    # Build text with two clear sentence groups
    first = " ".join(f"alpha{i}." for i in range(200))
    second = " ".join(f"beta{i}." for i in range(200))
    text = first + " " + second
    chunks = split_text(text, max_words=200, overlap_words=30)
    assert len(chunks) >= 2
    # The second chunk should contain some words from the first group (overlap)
    combined = " ".join(chunks[1:])
    assert any(f"alpha{i}" in combined for i in range(170, 200))


def test_very_long_single_sentence_hard_split() -> None:
    # One sentence with 500 words (no punctuation boundary)
    long_sentence = " ".join(f"w{i}" for i in range(500))
    chunks = split_text(long_sentence, max_words=350, overlap_words=0)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.split()) <= 350


def test_no_empty_chunks() -> None:
    text = "Sentence one. Sentence two. Sentence three."
    for chunk in split_text(text):
        assert chunk.strip() != ""


# ---------------------------------------------------------------------------
# Chunk.locator_text
# ---------------------------------------------------------------------------

def _chunk(locator: Locator) -> Chunk:
    return Chunk(source_id="s1", source_type="pdf", text="t", locator=locator)


def test_locator_text_page() -> None:
    assert _chunk(Locator(page=4)).locator_text() == "page 4"


def test_locator_text_slide() -> None:
    assert _chunk(Locator(slide=7)).locator_text() == "slide 7"


def test_locator_text_seconds_under_hour() -> None:
    assert _chunk(Locator(start_seconds=202)).locator_text() == "at 3:22"


def test_locator_text_seconds_over_hour() -> None:
    assert _chunk(Locator(start_seconds=3661)).locator_text() == "at 1:01:01"


def test_locator_text_heading() -> None:
    assert _chunk(Locator(heading="Introduction")).locator_text() == 'section "Introduction"'


def test_locator_text_empty() -> None:
    assert _chunk(Locator()).locator_text() == ""
