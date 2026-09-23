"""Test fakes: FakeLLM and FakeEmbedder — no network, no model download."""
import hashlib
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
from pydantic import BaseModel

from app.models.llm import Message


class FakeLLM:
    """Scriptable LLM fake that records every call."""

    def __init__(self, script: list[str] | None = None) -> None:
        # script is a list of strings returned in order; cycles if exhausted
        self._script = script or ["fake response"]
        self._idx = 0
        self.calls: list[dict[str, Any]] = []

    def _next(self) -> str:
        text = self._script[self._idx % len(self._script)]
        self._idx += 1
        return text

    def _record(self, messages: list[Message], system: str | None) -> None:
        self.calls.append({"messages": messages, "system": system})

    async def stream_chat(  # type: ignore[override]
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Real async generator — yields in ~4-char pieces to simulate streaming."""
        self._record(messages, system)
        text = self._next()
        chunk_size = 4
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        self._record(messages, system)
        return self._next()

    async def complete_json(
        self,
        messages: list[Message],
        system: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel:
        self._record(messages, system)
        raw = self._next()
        return schema.model_validate_json(raw)


class FakeLLMWithRateLimit:
    """Fake LLM that yields some tokens then raises a rate-limit error."""

    def __init__(
        self,
        tokens_before_error: list[str],
        error_code: str = "LLM_RATE_LIMIT",
        error_message: str = "LLM rate limit hit. Retry after 5s.",
    ) -> None:
        self._tokens_before_error = tokens_before_error
        self._idx = 0
        self._error_code = error_code
        self._error_message = error_message
        self.calls: list[dict[str, Any]] = []

    async def stream_chat(  # type: ignore[override]
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        self.calls.append({"messages": messages, "system": system})
        # Yield some tokens first
        for token in self._tokens_before_error:
            yield token
        # Then raise rate limit error
        from app.core.errors import AppError
        raise AppError(self._error_code, self._error_message, 502)

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append({"messages": messages, "system": system})
        return "".join(self._tokens_before_error)

    async def complete_json(
        self,
        messages: list[Message],
        system: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel:
        self.calls.append({"messages": messages, "system": system})
        raw = "".join(self._tokens_before_error)
        return schema.model_validate_json(raw)


class FakeEmbedder:
    """Deterministic bag-of-words embedder (dim=256). No model download."""

    DIM = 256

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.DIM, dtype=np.float32)
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Return (N, 256) float32 L2-normalised array."""
        return np.stack([self._embed_one(t) for t in texts])

    async def embed_query(self, text: str) -> np.ndarray:
        """Return (256,) float32 array."""
        return self._embed_one(text)
