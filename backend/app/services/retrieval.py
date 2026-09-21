"""Retrieval service: embed a query and fetch top-k chunks above min score."""
import logging

from app.core.config import get_settings
from app.models.chunk import Chunk
from app.services.embeddings import Embedder, get_embedder
from app.services.stores.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)


class Retriever:
    """Wraps embedder + vector store to answer a query for a session."""

    def __init__(self, embedder: Embedder, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def retrieve(
        self,
        session_id: str,
        query: str,
        source_ids: list[str] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Return (chunk, score) pairs above min_score, ordered by score desc.

        Falls back to settings defaults for top_k and min_score.
        """
        settings = get_settings()
        k = top_k if top_k is not None else settings.RETRIEVAL_TOP_K
        threshold = min_score if min_score is not None else settings.RETRIEVAL_MIN_SCORE

        query_vec = await self._embedder.embed_query(query)
        results = self._store.query(session_id, query_vec, top_k=k, source_ids=source_ids)
        filtered = [(chunk, score) for chunk, score in results if score >= threshold]
        logger.debug(
            "Retrieval session=%s query=%r top_k=%d results=%d above_threshold=%d",
            session_id, query, k, len(results), len(filtered),
        )
        return filtered


def get_retriever() -> Retriever:
    """Return a Retriever using the default embedder and vector store."""
    return Retriever(embedder=get_embedder(), store=get_vector_store())
