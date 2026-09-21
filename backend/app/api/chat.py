"""Chat SSE route."""
import logging
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.chat import chat_stream
from app.services.stores.session_store import get_session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class ChatBody(BaseModel):
    message: str
    mode: Literal["normal", "simple"] = "normal"


@router.post("/sessions/{sid}/chat")
async def chat(sid: str, body: ChatBody) -> StreamingResponse:
    """Stream a RAG chat response as SSE."""
    session = get_session_store().get(sid)
    return StreamingResponse(
        chat_stream(session, body.message, body.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
