"""Generate a summary and topic list for an ingested source."""
import logging

from pydantic import BaseModel

from app.models.chunk import Chunk
from app.models.llm import Message
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

# Use at most this many chunks and this many characters of combined text so we
# never accidentally send a huge payload to the LLM.
_MAX_CHUNKS = 30
_MAX_CHARS = 12_000

_SYSTEM = (
    "You are a concise summariser. Given text chunks from a document, "
    "return a JSON object with two fields: "
    '"summary" (2-4 sentence plain-English summary) and '
    '"topics" (list of 3-7 short topic strings).'
)


class _SummarySchema(BaseModel):
    summary: str
    topics: list[str]


async def summarise_source(
    chunks: list[Chunk],
    *,
    llm: LLMClient | None = None,
) -> tuple[str | None, list[str]]:
    """Return (summary, topics) for the given chunks.

    Uses at most ``_MAX_CHUNKS`` chunks and ``_MAX_CHARS`` characters of
    combined text to stay within context limits. Returns ``(None, [])`` on
    any failure so the caller can surface partial results without crashing.
    """
    _llm = llm or get_llm()
    sample = chunks[:_MAX_CHUNKS]
    combined = "\n\n".join(c.text for c in sample)
    # Truncate at character level as a hard safety net
    if len(combined) > _MAX_CHARS:
        combined = combined[:_MAX_CHARS]
        logger.debug("summarise_source: truncated combined text to %d chars", _MAX_CHARS)
    messages = [Message(role="user", content=f"Chunks:\n{combined}")]
    try:
        result = await _llm.complete_json(messages, system=_SYSTEM, schema=_SummarySchema)
        return result.summary or None, result.topics
    except Exception as exc:
        logger.warning("summarise_source failed: %s", exc)
        return None, []
