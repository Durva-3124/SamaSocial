"""Sentence-aware text splitter used by all ingestors."""
import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_text(text: str, max_words: int = 350, overlap_words: int = 50) -> list[str]:
    """Split text into chunks of at most max_words words with overlap.

    Splits on sentence boundaries where possible; hard-splits sentences that
    exceed max_words on their own.
    """
    text = " ".join(text.split())
    if not text:
        return []

    sentences = _SENTENCE_END.split(text)

    # Hard-split any sentence that exceeds max_words
    expanded: list[str] = []
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            expanded.append(sent)
        else:
            for i in range(0, len(words), max_words):
                expanded.append(" ".join(words[i : i + max_words]))

    chunks: list[str] = []
    current: list[str] = []
    current_count = 0

    for sent in expanded:
        word_count = len(sent.split())
        if current_count + word_count > max_words and current:
            chunks.append(" ".join(current))
            # carry overlap
            overlap: list[str] = []
            overlap_count = 0
            for s in reversed(current):
                wc = len(s.split())
                if overlap_count + wc > overlap_words:
                    break
                overlap.insert(0, s)
                overlap_count += wc
            current = overlap
            current_count = overlap_count
        current.append(sent)
        current_count += word_count

    if current:
        chunks.append(" ".join(current))

    return chunks
