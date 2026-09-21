"""Tests for app/services/llm.py — offline, httpx patched with unittest.mock."""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.errors import AppError
from app.models.llm import Message
from app.services.llm import OpenAICompatClient, _strip_fences

BASE = "https://api.groq.com/openai/v1"


def _setup_env() -> None:
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_MODEL"] = "test-model"
    os.environ["LLM_BASE_URL"] = BASE
    from app.core.config import get_settings
    get_settings.cache_clear()


def _sse_lines(*deltas: str) -> list[str]:
    lines = []
    for d in deltas:
        chunk = {"choices": [{"delta": {"content": d}}]}
        lines.append(f"data: {json.dumps(chunk)}")
    lines.append("data: [DONE]")
    return lines


def _completion_json(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


# ---------------------------------------------------------------------------
# _strip_fences
# ---------------------------------------------------------------------------

def test_strip_fences_plain() -> None:
    assert _strip_fences('{"a":1}') == '{"a":1}'


def test_strip_fences_with_backticks() -> None:
    assert _strip_fences("```json\n{\"a\":1}\n```") == '{"a":1}'


# ---------------------------------------------------------------------------
# Helpers to build mock httpx responses
# ---------------------------------------------------------------------------

def _mock_stream_response(status: int, lines: list[str], headers: dict | None = None) -> MagicMock:
    """Build a mock streaming response for client.stream(...)."""
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}

    async def _aiter_lines():
        for line in lines:
            yield line

    resp.aiter_lines = _aiter_lines

    if status >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status = MagicMock(
            side_effect=HTTPStatusError(
                "error", request=Request("POST", BASE), response=Response(status)
            )
        )
    else:
        resp.raise_for_status = MagicMock()

    # Make it usable as async context manager
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_post_response(status: int, body: dict) -> MagicMock:
    """Build a mock non-streaming response for client.post(...)."""
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {}
    resp.json = MagicMock(return_value=body)

    if status >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status = MagicMock(
            side_effect=HTTPStatusError(
                "error", request=Request("POST", BASE), response=Response(status)
            )
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# stream_chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_yields_tokens() -> None:
    _setup_env()
    stream_cm = _mock_stream_response(200, _sse_lines("Hello", " world"))

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=stream_cm)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm.httpx.AsyncClient", return_value=mock_client):
        tokens: list[str] = []
        async for tok in OpenAICompatClient().stream_chat([Message(role="user", content="hi")]):
            tokens.append(tok)
    assert "".join(tokens) == "Hello world"


@pytest.mark.asyncio
async def test_stream_chat_401_raises_llm_auth() -> None:
    _setup_env()
    stream_cm = _mock_stream_response(401, [])

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=stream_cm)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AppError) as exc_info:
            async for _ in OpenAICompatClient().stream_chat([Message(role="user", content="hi")]):
                pass
    assert exc_info.value.code == "LLM_AUTH"


@pytest.mark.asyncio
async def test_stream_chat_429_raises_rate_limit() -> None:
    _setup_env()
    from httpx import HTTPStatusError, Request, Response as HResp
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {"retry-after": "5"}
    resp.raise_for_status = MagicMock(
        side_effect=HTTPStatusError("429", request=Request("POST", BASE), response=HResp(429, headers={"retry-after": "5"}))
    )
    stream_cm = AsyncMock()
    stream_cm.__aenter__ = AsyncMock(return_value=resp)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=stream_cm)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.llm.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AppError) as exc_info:
            async for _ in OpenAICompatClient().stream_chat([Message(role="user", content="hi")]):
                pass
    assert exc_info.value.code == "LLM_RATE_LIMIT"
    assert "5" in exc_info.value.message


# ---------------------------------------------------------------------------
# complete_json
# ---------------------------------------------------------------------------

class _Schema(BaseModel):
    answer: str


def _patch_complete(responses: list[dict]):
    """Patch httpx.AsyncClient.post to return successive responses."""
    call_count = {"n": 0}

    async def _fake_post(*args, **kwargs):
        r = responses[min(call_count["n"], len(responses) - 1)]
        call_count["n"] += 1
        return _mock_post_response(200, r)

    mock_client = AsyncMock()
    mock_client.post = _fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_complete_json_success() -> None:
    _setup_env()
    mc = _patch_complete([_completion_json('{"answer":"yes"}')])
    with patch("app.services.llm.httpx.AsyncClient", return_value=mc):
        result = await OpenAICompatClient().complete_json(
            [Message(role="user", content="q")], system="sys", schema=_Schema
        )
    assert result.answer == "yes"


@pytest.mark.asyncio
async def test_complete_json_retry_then_success() -> None:
    _setup_env()
    mc = _patch_complete([
        _completion_json("not json"),
        _completion_json('{"answer":"fixed"}'),
    ])
    with patch("app.services.llm.httpx.AsyncClient", return_value=mc):
        result = await OpenAICompatClient().complete_json(
            [Message(role="user", content="q")], system="sys", schema=_Schema
        )
    assert result.answer == "fixed"


@pytest.mark.asyncio
async def test_complete_json_retry_then_fail() -> None:
    _setup_env()
    mc = _patch_complete([_completion_json("bad"), _completion_json("still bad")])
    with patch("app.services.llm.httpx.AsyncClient", return_value=mc):
        with pytest.raises(AppError) as exc_info:
            await OpenAICompatClient().complete_json(
                [Message(role="user", content="q")], system="sys", schema=_Schema
            )
    assert exc_info.value.code == "LLM_INVALID_JSON"
