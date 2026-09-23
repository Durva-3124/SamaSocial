import logging
import re
from collections.abc import AsyncIterator

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.sse import sse as _sse
from app.models.chunk import Chunk
from app.models.llm import Message
from app.models.session import Session
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient, get_llm
from app.services.prompts import CITATION_RULE, GROUNDED_SYSTEM, SIMPLE_SYSTEM
from app.services.retrieval import Retriever
from app.services.stores.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)

_CITATION_RULE = CITATION_RULE
_SYSTEM_NORMAL = GROUNDED_SYSTEM
_SYSTEM_SIMPLE = SIMPLE_SYSTEM


def _build_context_block(chunks_with_scores: list[tuple[Chunk, float]]) -> tuple[str, list[dict]]:
    """Build the context string and citation metadata list from retrieved chunks."""
    lines: list[str] = []
    citations: list[dict] = []
    for i, (chunk, score) in enumerate(chunks_with_scores, start=1):
        label = f"S{i}"
        lines.append(f"[{label}] {chunk.text}")
        citations.append({
            "label": label,
            "source_id": chunk.source_id,
            "locator": chunk.locator.model_dump(exclude_none=True),
            "locator_text": chunk.locator_text(),
            "snippet": chunk.text[:200],
            "score": score,
        })
    return "\n\n".join(lines), citations


async def chat_stream(
    session: Session,
    message: str,
    mode: str,
    *,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    """Yield SSE strings: token*, citations, done  (or error on failure)."""
    _llm = llm or get_llm()
    _emb = embedder or get_embedder()
    _vs = vector_store or get_vector_store()

    retriever = Retriever(embedder=_emb, store=_vs)

    try:
        results = await retriever.retrieve(session.id, message)
    except Exception as exc:
        logger.exception("Retrieval failed")
        yield _sse("error", {"code": "RETRIEVAL_ERROR", "message": str(exc)})
        return

    declined = len(results) == 0
    context_block, citation_meta = _build_context_block(results)

    system = _SYSTEM_SIMPLE if mode == "simple" else _SYSTEM_NORMAL

    if declined:
        user_content = message
    else:
        user_content = f"Context:\n{context_block}\n\nQuestion: {message}"

    history = list(session.history)
    messages = history + [Message(role="user", content=user_content)]

    full_response = ""
    try:
        async for token in _llm.stream_chat(messages, system=system, temperature=temperature):
            full_response += token
            yield _sse("token", {"text": token})
    except AppError as exc:
        if exc.code == "LLM_RATE_LIMIT":
            logger.warning("LLM rate limit hit during streaming: %s", exc.message)
            yield _sse("error", {"code": "LLM_RATE_LIMIT", "message": "The assistant is temporarily rate-limited, please try again in a moment"})
        else:
            logger.exception("LLM streaming failed: %s", exc.message)
            yield _sse("error", {"code": exc.code, "message": exc.message})
        return
    except Exception as exc:
        logger.exception("LLM streaming failed")
        yield _sse("error", {"code": "LLM_ERROR", "message": str(exc)})
        return

    # Persist turn to history (store original message, not context-augmented)
    session.history.append(Message(role="user", content=message))
    session.history.append(Message(role="assistant", content=full_response))

    # Emit citations (only chunks whose label appears in the response)
    visible = [
        {k: v for k, v in c.items() if k != "score"}
        for c in citation_meta
        if f"[{c['label']}]" in full_response
    ]
    # Enrich with source name/type from session
    for item in visible:
        src = session.sources.get(item["source_id"])
        item["source_name"] = src.name if src else item["source_id"]
        item["source_type"] = src.type if src else "web"

    # Safety net: log structured warning if no [S#] tags found despite retrieved context above threshold
    tags_found = re.findall(r"\[S\d+\]", full_response)
    if not tags_found and citation_meta:
        top_score = max(c["score"] for c in citation_meta)
        threshold = get_settings().RETRIEVAL_MIN_SCORE
        if top_score >= threshold:
            logger.warning(
                "citation_omission session=%s top_score=%.4f chunks=%d "
                "response_len=%d — model returned no [S#] tags despite grounded context",
                session.id,
                top_score,
                len(citation_meta),
                len(full_response),
                extra={
                    "event": "citation_omission",
                    "session_id": session.id,
                    "top_score": top_score,
                    "chunks": len(citation_meta),
                    "response_len": len(full_response),
                },
            )

    if visible:
        yield _sse("citations", {"items": visible})

    used_ids = list({item["source_id"] for item in visible})
    yield _sse("done", {"declined": declined, "used_source_ids": used_ids})
