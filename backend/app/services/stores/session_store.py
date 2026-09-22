"""In-memory session store with TTL eviction."""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.session import Session

logger = logging.getLogger(__name__)


class SessionStore:
    """Thread-safe in-memory store for Session objects with TTL eviction."""

    def __init__(self, ttl_minutes: int) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def create(self) -> Session:
        """Create and store a new session, returning it."""
        session = Session(id=uuid.uuid4().hex)
        with self._lock:
            self._evict()
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session:
        """Return the session or raise AppError(404)."""
        with self._lock:
            self._evict()
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_active = datetime.now(UTC)
        if session is None:
            raise AppError("SESSION_NOT_FOUND", f"Session {session_id!r} not found", 404)
        return session

    def delete(self, session_id: str) -> None:
        """Remove a session if it exists (idempotent)."""
        with self._lock:
            self._sessions.pop(session_id, None)
        self._free_vectors(session_id)

    def _evict(self) -> None:
        """Remove sessions whose last_active is older than TTL (call under lock)."""
        cutoff = datetime.now(UTC) - self._ttl
        expired = [sid for sid, s in self._sessions.items() if s.last_active < cutoff]
        for sid in expired:
            logger.debug("Evicting expired session %s", sid)
            del self._sessions[sid]
            self._free_vectors(sid)

    def _free_vectors(self, session_id: str) -> None:
        """Delete embeddings for a session from the vector store."""
        try:
            from app.services.stores.vector_store import get_vector_store
            get_vector_store().clear_session(session_id)
        except Exception:
            logger.debug("Vector store cleanup skipped for %s", session_id)


@lru_cache
def get_session_store() -> SessionStore:
    """Return the singleton SessionStore."""
    return SessionStore(ttl_minutes=get_settings().SESSION_TTL_MINUTES)
