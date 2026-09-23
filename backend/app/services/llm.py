"""Provider-agnostic LLM client with streaming and validated JSON output."""
import asyncio as _asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.llm import Message

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _messages_payload(messages: list[Message], system: str | None) -> list[dict]:
    payload: list[dict] = []
    if system:
        payload.append({"role": "system", "content": system})
    payload.extend({"role": m.role, "content": m.content} for m in messages)
    return payload


def _map_http_error(exc: httpx.HTTPStatusError) -> AppError:
    status = exc.response.status_code
    if status == 401:
        return AppError("LLM_AUTH", "Invalid LLM API key.", 502)
    if status == 429:
        retry = exc.response.headers.get("retry-after", "")
        msg = f"LLM rate limit hit.{f' Retry after {retry}s.' if retry else ''}"
        return AppError("LLM_RATE_LIMIT", msg, 502)
    return AppError("LLM_ERROR", f"LLM provider returned {status}.", 502)




@runtime_checkable
class LLMClient(Protocol):
    """Protocol every LLM backend must satisfy."""

    async def stream_chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]: ...  # implementations are async generators

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> str: ...

    async def complete_json(
        self,
        messages: list[Message],
        system: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel: ...


class OpenAICompatClient:
    """OpenAI-compatible HTTP client (works with Groq, OpenAI, Gemini, etc.)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base = settings.LLM_BASE_URL.rstrip("/")
        self._model = settings.LLM_MODEL
        self._headers = {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        self._timeout = httpx.Timeout(30.0)

    async def stream_chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Stream chat completion, yielding delta text chunks.

        Retries once on 429 only when Retry-After <= 10 s and no token has
        been yielded yet.  On a second 429, or Retry-After > 10 s, raises
        AppError("LLM_RATE_LIMIT").
        """
        _MAX_RETRY_WAIT = 10
        payload = {
            "model": self._model,
            "messages": _messages_payload(messages, system),
            "temperature": temperature,
            "stream": True,
        }

        for attempt in range(2):
            _retry = False
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self._base}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    ) as resp:
                        try:
                            resp.raise_for_status()
                        except httpx.HTTPStatusError as exc:
                            if exc.response.status_code == 429 and attempt == 0:
                                wait = int(exc.response.headers.get("retry-after", "2"))
                                if wait > _MAX_RETRY_WAIT:
                                    raise _map_http_error(exc) from exc
                                logger.warning("Rate limited, retrying after %ss", wait)
                                await _asyncio.sleep(wait)
                                _retry = True
                            else:
                                raise _map_http_error(exc) from exc

                        if not _retry:
                            async for line in resp.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    return
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk["choices"][0]["delta"].get("content") or ""
                                    if delta:
                                        yield delta
                                except (KeyError, json.JSONDecodeError):
                                    continue
                            return  # success — exit retry loop
            except httpx.TimeoutException as exc:
                raise AppError("LLM_TIMEOUT", "LLM request timed out.", 502) from exc
            except AppError:
                raise
            if not _retry:
                return
        # Exhausted both attempts — second was also 429
        raise AppError("LLM_RATE_LIMIT", "LLM rate limit hit after retry.", 502)

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Non-streaming completion, returns full text."""
        payload = {
            "model": self._model,
            "messages": _messages_payload(messages, system),
            "temperature": temperature,
            "stream": False,
        }
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self._base}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429 and attempt == 0:
                            retry_after = int(exc.response.headers.get("retry-after", "2"))
                            if retry_after <= 10:
                                logger.warning("Rate limited, retrying after %ss", retry_after)
                                await _asyncio.sleep(retry_after)
                                continue
                        raise _map_http_error(exc) from exc
                    return resp.json()["choices"][0]["message"]["content"]
            except httpx.TimeoutException as exc:
                raise AppError("LLM_TIMEOUT", "LLM request timed out.", 502) from exc
        raise AppError("LLM_RATE_LIMIT", "LLM rate limit hit after retry.", 502)

    async def complete_json(
        self,
        messages: list[Message],
        system: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel:
        """Complete and parse/validate JSON against a Pydantic schema. Retries once."""
        schema_hint = json.dumps(schema.model_json_schema(), indent=2)
        system_with_schema = (
            f"{system}\n\nRespond with valid JSON matching this schema:\n{schema_hint}"
        )
        msgs = list(messages)

        for attempt in range(2):
            raw = await self.complete(msgs, system=system_with_schema, temperature=temperature)
            text = _strip_fences(raw)
            try:
                return schema.model_validate_json(text)
            except Exception as exc:
                if attempt == 0:
                    logger.warning("complete_json attempt 1 failed: %s", exc)
                    msgs = msgs + [
                        Message(role="assistant", content=raw),
                        Message(
                            role="user",
                            content=f"Your previous output was invalid: {exc}. Return only corrected JSON.",
                        ),
                    ]
                else:
                    raise AppError(
                        "LLM_INVALID_JSON",
                        "LLM returned invalid JSON after retry.",
                        502,
                    ) from exc
        raise AppError("LLM_INVALID_JSON", "LLM returned invalid JSON.", 502)


@lru_cache
def get_llm() -> OpenAICompatClient:
    """Return a cached LLM client instance."""
    return OpenAICompatClient()
