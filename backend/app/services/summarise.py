"""Generate a summary and topic list for an ingested source."""
import logging

from pydantic import BaseModel

from app.models.chunk import Chunk
from app.models.llm import Message
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

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
) -> tuple[str, list[str]]:
    """Return (summary, topics) for the given chunks.

    Uses up to the first 30 chunks to stay within context limits.
    """
    _llm = llm or get_llm()
    sample = chunks[:30]
    combined = "\n\n".join(c.text for c in sample)
    messages = [Message(role="user", content=f"Chunks:\n{combined}")]
    try:
        result = await _llm.complete_json(messages, system=_SYSTEM, schema=_SummarySchema)
        return result.summary, result.topics
    except Exception as exc:
        logger.warning("summarise_source failed: %s", exc)
        return "", []
