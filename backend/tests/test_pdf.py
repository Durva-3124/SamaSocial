"""Tests for PDF ingestion — PDFs built in-test with fitz, no fixture files."""
import pytest
import fitz

from app.core.errors import AppError
from app.services.ingestion.pdf import ingest_pdf


def _make_pdf(pages: list[str]) -> bytes:
    """Build a minimal PDF with one text block per page."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=12)
    buf = doc.tobytes()
    doc.close()
    return buf


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_three_page_pdf_correct_page_numbers() -> None:
    data = _make_pdf(["Alpha content here.", "Beta content here.", "Gamma content here."])
    result = ingest_pdf("src1", "test.pdf", data)
    assert result.source_type == "pdf"
    assert result.name == "test.pdf"
    page_nums = {c.locator.page for c in result.chunks}
    assert page_nums == {1, 2, 3}
    texts = " ".join(c.text for c in result.chunks)
    assert "Alpha" in texts
    assert "Beta" in texts
    assert "Gamma" in texts


def test_chunks_have_correct_source_id() -> None:
    data = _make_pdf(["Some text on page one."])
    result = ingest_pdf("my-source", "f.pdf", data)
    assert all(c.source_id == "my-source" for c in result.chunks)


def test_no_chunk_exceeds_max_words() -> None:
    # 20 pages of ~400 words each
    long_page = " ".join(f"word{i}." for i in range(400))
    data = _make_pdf([long_page] * 20)
    result = ingest_pdf("s", "big.pdf", data)
    for chunk in result.chunks:
        assert len(chunk.text.split()) <= 350


def test_no_empty_chunks() -> None:
    data = _make_pdf(["Hello world."])
    result = ingest_pdf("s", "f.pdf", data)
    for chunk in result.chunks:
        assert chunk.text.strip() != ""


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_blank_pdf_raises_no_text_layer() -> None:
    data = _make_pdf(["", "", ""])  # all blank pages
    with pytest.raises(AppError) as exc_info:
        ingest_pdf("s", "blank.pdf", data)
    assert exc_info.value.code == "NO_TEXT_LAYER"


def test_garbage_bytes_raise_invalid_pdf() -> None:
    with pytest.raises(AppError) as exc_info:
        ingest_pdf("s", "bad.pdf", b"not a pdf at all")
    assert exc_info.value.code == "INVALID_PDF"


# ---------------------------------------------------------------------------
# Blank page warning
# ---------------------------------------------------------------------------

def test_blank_page_warning_when_over_threshold() -> None:
    # 1 text page + 4 blank pages → 80% blank → warning
    data = _make_pdf(["Real content here with enough words."] + [""] * 4)
    result = ingest_pdf("s", "f.pdf", data)
    assert any("blank" in w.lower() for w in result.warnings)


def test_no_warning_when_under_threshold() -> None:
    # 3 text pages + 0 blank → no warning
    data = _make_pdf(["Page one text.", "Page two text.", "Page three text."])
    result = ingest_pdf("s", "f.pdf", data)
    assert result.warnings == []
