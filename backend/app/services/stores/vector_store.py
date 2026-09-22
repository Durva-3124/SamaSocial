"""In-memory NumPy vector store keyed by session."""
from functools import lru_cache
from threading import Lock

import numpy as np

from app.models.chunk import Chunk


class VectorStore:
    """Per-session chunk + embedding store backed by NumPy arrays."""

    def __init__(self) -> None:
        # session_id -> (chunks list, (N, dim) float32 matrix)
        self._data: dict[str, tuple[list[Chunk], np.ndarray]] = {}
        self._lock = Lock()

    def add(self, session_id: str, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """Append chunks and their embeddings for a session.

        embeddings must be L2-normalised and shape (len(chunks), dim).
        """
        with self._lock:
            if session_id not in self._data:
                self._data[session_id] = (list(chunks), embeddings.astype(np.float32))
            else:
                existing_chunks, existing_vecs = self._data[session_id]
                merged_chunks = existing_chunks + list(chunks)
                merged_vecs = np.vstack([existing_vecs, embeddings.astype(np.float32)])
                self._data[session_id] = (merged_chunks, merged_vecs)

    def remove_source(self, session_id: str, source_id: str) -> None:
        """Remove all chunks belonging to source_id from a session."""
        with self._lock:
            if session_id not in self._data:
                return
            chunks, vecs = self._data[session_id]
            keep = [i for i, c in enumerate(chunks) if c.source_id != source_id]
            if not keep:
                del self._data[session_id]
                return
            self._data[session_id] = (
                [chunks[i] for i in keep],
                vecs[keep],
            )

    def query(
        self,
        session_id: str,
        query_vec: np.ndarray,
        top_k: int,
        source_ids: list[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Return up to top_k (chunk, cosine_score) pairs, highest score first.

        query_vec must be L2-normalised, shape (dim,).
        If source_ids is given, only chunks from those sources are considered.
        """
        with self._lock:
            entry = self._data.get(session_id)
        if entry is None:
            return []
        chunks, vecs = entry
        if source_ids is not None:
            indices = [i for i, c in enumerate(chunks) if c.source_id in source_ids]
            if not indices:
                return []
            filtered_chunks = [chunks[i] for i in indices]
            filtered_vecs = vecs[indices]
        else:
            filtered_chunks = chunks
            filtered_vecs = vecs

        scores: np.ndarray = filtered_vecs @ query_vec  # cosine (already normalised)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(filtered_chunks[i], float(scores[i])) for i in top_indices]

    def all_chunks(
        self,
        session_id: str,
        source_ids: list[str] | None = None,
    ) -> list[Chunk]:
        """Return all chunks for a session, optionally filtered by source_ids."""
        with self._lock:
            entry = self._data.get(session_id)
        if entry is None:
            return []
        chunks, _ = entry
        if source_ids is not None:
            return [c for c in chunks if c.source_id in source_ids]
        return list(chunks)

    def clear_session(self, session_id: str) -> None:
        """Remove all data for a session."""
        with self._lock:
            self._data.pop(session_id, None)


@lru_cache
def get_vector_store() -> VectorStore:
    """Return the singleton VectorStore."""
    return VectorStore()
