"""Quiz endpoint."""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.errors import AppError
from app.services.llm import get_llm
from app.services.quiz import generate_quiz
from app.services.stores.session_store import get_session_store
from app.services.stores.vector_store import get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class QuizBody(BaseModel):
    num_questions: int = 5
    source_ids: list[str] | None = None


@router.post("/sessions/{sid}/quiz")
async def quiz(sid: str, body: QuizBody) -> dict:
    """Generate multiple-choice quiz questions from session sources."""
    session = get_session_store().get(sid)
    vs = get_vector_store()

    # Collect chunks from the vector store via a broad query
    from app.services.embeddings import get_embedder
    embedder = get_embedder()
    import numpy as np
    # Use a zero vector to get all chunks (cosine with zero = 0, but we want all)
    # Instead, pull directly from the store's internal data
    entry = vs._data.get(session.id)
    if not entry:
        raise AppError("NO_SOURCES", "No sources have been ingested into this session.", 422)

    all_chunks, _ = entry
    if body.source_ids:
        chunks = [c for c in all_chunks if c.source_id in body.source_ids]
    else:
        chunks = list(all_chunks)

    if not chunks:
        raise AppError("NO_SOURCES", "No chunks found for the requested sources.", 422)

    questions = await generate_quiz(chunks, num_questions=body.num_questions, llm=get_llm())
    return {"questions": questions}
