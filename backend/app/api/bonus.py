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

    chunks = vs.all_chunks(session.id, source_ids=body.source_ids)
    if not chunks:
        raise AppError("NO_SOURCES", "No chunks found for the requested sources.", 422)

    questions = await generate_quiz(chunks, num_questions=body.num_questions, llm=get_llm())
    return {"questions": questions}
