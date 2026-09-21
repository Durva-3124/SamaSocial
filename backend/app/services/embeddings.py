"""Local embedding service using sentence-transformers."""
import asyncio
import logging
from functools import lru_cache
from typing import Protocol, runtime_checkable

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32


@runtime_checkable
class Embedder(Protocol):
    """Protocol every embedder backend must satisfy."""

    async def embed(self, texts: list[str]) -> np.ndarray: ...

    async def embed_query(self, text: str) -> np.ndarray: ...


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (arr / norms).astype(np.float32)


class SentenceTransformerEmbedder:
    """Lazy-loaded sentence-transformers embedder, runs encode in a thread."""

    def __init__(self) -> None:
        self._model = None
        self._lock = asyncio.Lock()

    def _load(self) -> None:
        """Load the model once (called from a thread)."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            self._model = SentenceTransformer(get_settings().EMBEDDING_MODEL)

    def _encode_sync(self, texts: list[str]) -> np.ndarray:
        self._load()
        results: list[np.ndarray] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            vecs = self._model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
            results.append(vecs)
        return _l2_normalize(np.vstack(results))

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts, returns (N, dim) float32 L2-normalised array."""
        return await asyncio.to_thread(self._encode_sync, texts)

    async def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query string, returns (dim,) float32 array."""
        arr = await self.embed([text])
        return arr[0]


@lru_cache
def get_embedder() -> SentenceTransformerEmbedder:
    """Return a cached embedder instance."""
    return SentenceTransformerEmbedder()
