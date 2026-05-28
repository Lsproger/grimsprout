"""Tests for grimsprout.services.llm.ollama_client (python-ollama based)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grimsprout.services.llm import ollama_client
from grimsprout.services.llm.ollama_client import LLMStats
from grimsprout.utils.errors import LLMResponseError

BASE_URL = "http://localhost:11434"
MODEL = "gemma3:4b"
MESSAGES = [{"role": "user", "content": "hello"}]

_MOCK_EVAL_COUNT = 38
_MOCK_EVAL_DURATION = 905_000_000  # nanoseconds
_MOCK_PROMPT_EVAL_COUNT = 26
_MOCK_TOTAL_DURATION = 1_300_000_000  # nanoseconds


def _make_chat_response(content: str = "answer text", tool_calls=None):
    """Build a minimal mock object resembling ollama.ChatResponse."""
    resp = MagicMock()
    resp.message.content = content
    resp.message.tool_calls = tool_calls
    resp.eval_count = _MOCK_EVAL_COUNT
    resp.eval_duration = _MOCK_EVAL_DURATION
    resp.prompt_eval_count = _MOCK_PROMPT_EVAL_COUNT
    resp.total_duration = _MOCK_TOTAL_DURATION
    return resp


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_success() -> None:
    mock_resp = _make_chat_response("Hello there.")
    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(return_value=mock_resp)

        content, stats = await ollama_client.chat(BASE_URL, MODEL, MESSAGES)

    assert content == "Hello there."
    assert isinstance(stats, LLMStats)
    assert stats.eval_count == _MOCK_EVAL_COUNT


@pytest.mark.asyncio
async def test_chat_empty_content_raises() -> None:
    mock_resp = _make_chat_response("")
    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(return_value=mock_resp)

        with pytest.raises(LLMResponseError, match="empty content"):
            await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


@pytest.mark.asyncio
async def test_chat_response_error_wraps() -> None:
    from ollama import ResponseError

    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(side_effect=ResponseError("model not found", status_code=404))

        with pytest.raises(LLMResponseError, match="Ollama error"):
            await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


@pytest.mark.asyncio
async def test_chat_timeout_wraps() -> None:
    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(side_effect=TimeoutError("timed out"))

        with pytest.raises(LLMResponseError, match="timeout"):
            await ollama_client.chat(BASE_URL, MODEL, MESSAGES, timeout_sec=5)


@pytest.mark.asyncio
async def test_chat_connection_error_wraps() -> None:
    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(side_effect=ConnectionRefusedError("connection refused"))

        with pytest.raises(LLMResponseError, match="connection error"):
            await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


# ---------------------------------------------------------------------------
# chat_with_tools()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_with_tools_returns_response_and_stats() -> None:
    tc = MagicMock()
    tc.function.name = "water"
    tc.function.arguments = {"plant_ids": ["areca_01"]}
    mock_resp = _make_chat_response(content="", tool_calls=[tc])

    tools = [{"type": "function", "function": {"name": "water"}}]

    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(return_value=mock_resp)

        resp, stats = await ollama_client.chat_with_tools(BASE_URL, MODEL, MESSAGES, tools)

    assert resp.message.tool_calls == [tc]
    assert isinstance(stats, LLMStats)


@pytest.mark.asyncio
async def test_chat_with_tools_no_tool_calls() -> None:
    """Model may choose not to call any tool — content is a plain reply."""
    mock_resp = _make_chat_response(content="Не понял вопроса.", tool_calls=None)
    tools = [{"type": "function", "function": {"name": "water"}}]

    with patch("grimsprout.services.llm.ollama_client.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat = AsyncMock(return_value=mock_resp)

        resp, stats = await ollama_client.chat_with_tools(BASE_URL, MODEL, MESSAGES, tools)

    assert resp.message.tool_calls is None
    assert resp.message.content == "Не понял вопроса."


# ---------------------------------------------------------------------------
# LLMStats extraction
# ---------------------------------------------------------------------------


def test_extract_stats_computes_tokens_per_sec() -> None:
    resp = _make_chat_response()
    stats = ollama_client._extract_stats(resp)
    expected_tps = _MOCK_EVAL_COUNT / _MOCK_EVAL_DURATION * 1e9
    assert stats.tokens_per_sec == pytest.approx(expected_tps, rel=1e-3)
    assert stats.eval_count == _MOCK_EVAL_COUNT
    assert stats.prompt_eval_count == _MOCK_PROMPT_EVAL_COUNT
    assert stats.total_duration_ms == pytest.approx(_MOCK_TOTAL_DURATION / 1e6, rel=1e-3)


def test_extract_stats_no_fields() -> None:
    resp = MagicMock()
    resp.eval_count = None
    resp.eval_duration = None
    resp.prompt_eval_count = None
    resp.total_duration = None
    stats = ollama_client._extract_stats(resp)
    assert stats.tokens_per_sec is None
    assert stats.eval_count is None
    assert stats.total_duration_ms is None
