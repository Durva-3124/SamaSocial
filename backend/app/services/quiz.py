"""Generate multiple-choice quiz questions from session chunks."""
import logging

from pydantic import BaseModel, Field

from app.models.chunk import Chunk
from app.models.llm import Message
from app.services.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a quiz generator. Given context chunks, produce exactly {n} "
    "multiple-choice questions. Each question must have exactly 4 options and one correct answer. "
    "Return a JSON object: {{\"questions\": [{{\"question\", \"options\": [4 strings], "
    "\"answer_index\": 0-3, \"explanation\", \"source_id\", \"locator_text\"}}]}}. "
    "Use only information from the provided chunks."
)


class _Question(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str
    source_id: str
    locator_text: str


class _QuizSchema(BaseModel):
    questions: list[_Question]


async def generate_quiz(
    chunks: list[Chunk],
    num_questions: int = 5,
    *,
    llm: LLMClient | None = None,
) -> list[dict]:
    """Return a list of question dicts matching the API contract.

    Uses up to 20 chunks as context.
    """
    _llm = llm or get_llm()
    sample = chunks[:20]
    context = "\n\n".join(
        f"[source_id={c.source_id} locator={c.locator_text()}] {c.text}"
        for c in sample
    )
    system = _SYSTEM.format(n=num_questions)
    messages = [Message(role="user", content=f"Chunks:\n{context}")]
    result = await _llm.complete_json(messages, system=system, schema=_QuizSchema)
    return [q.model_dump() for q in result.questions[:num_questions]]
