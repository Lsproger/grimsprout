"""Tests for grimsprout.services.llm.ollama_client."""

from __future__ import annotations

import json

import httpx
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


def _mock_response(content_dict: dict, *, include_stats: bool = True) -> httpx.Response:
    body: dict = {"message": {"role": "assistant", "content": json.dumps(content_dict)}, "done": True}
    if include_stats:
        body.update(
            eval_count=_MOCK_EVAL_COUNT,
            eval_duration=_MOCK_EVAL_DURATION,
            prompt_eval_count=_MOCK_PROMPT_EVAL_COUNT,
            prompt_eval_duration=350_000_000,
            total_duration=_MOCK_TOTAL_DURATION,
        )
    return httpx.Response(200, json=body, request=httpx.Request("POST", "http://localhost:11434/api/chat"))


@pytest.mark.asyncio
async def test_chat_success(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"action": "water", "confidence": 0.9}

    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        return _mock_response(expected)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    result, stats = await ollama_client.chat(BASE_URL, MODEL, MESSAGES)
    assert result == expected
    assert isinstance(stats, LLMStats)


@pytest.mark.asyncio
async def test_chat_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with pytest.raises(LLMResponseError, match="timeout"):
        await ollama_client.chat(BASE_URL, MODEL, MESSAGES, timeout_sec=5)


@pytest.mark.asyncio
async def test_chat_http_500(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        resp = httpx.Response(500, text="internal error", request=httpx.Request("POST", url))
        resp.raise_for_status()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with pytest.raises(LLMResponseError, match="500"):
        await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


@pytest.mark.asyncio
async def test_chat_invalid_json_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        body = {"message": {"role": "assistant", "content": "not json at all"}, "done": True}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with pytest.raises(LLMResponseError, match="Invalid JSON"):
        await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


@pytest.mark.asyncio
async def test_chat_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        body = {"message": {"role": "assistant", "content": ""}, "done": True}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with pytest.raises(LLMResponseError, match="empty content"):
        await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


@pytest.mark.asyncio
async def test_chat_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with pytest.raises(LLMResponseError, match="connection error"):
        await ollama_client.chat(BASE_URL, MODEL, MESSAGES)


@pytest.mark.asyncio
async def test_chat_format_schema_passed_as_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """When format_schema is provided, the payload 'format' field should be the dict."""
    schema = {"type": "object", "properties": {"action": {"type": "string"}}}
    captured: dict = {}

    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        captured["payload"] = kwargs.get("json", {})
        return _mock_response({"action": "water", "confidence": 0.9})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    await ollama_client.chat(BASE_URL, MODEL, MESSAGES, format_schema=schema)
    assert captured["payload"]["format"] == schema
    assert captured["payload"]["options"]["top_p"] == 0.95
    assert captured["payload"]["options"]["top_k"] == 64


@pytest.mark.asyncio
async def test_chat_no_format_schema_uses_json_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """When format_schema is None (default), 'format' should be the string 'json'."""
    captured: dict = {}

    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        captured["payload"] = kwargs.get("json", {})
        return _mock_response({"action": "water", "confidence": 0.9})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    await ollama_client.chat(BASE_URL, MODEL, MESSAGES)
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["options"]["top_p"] == 0.95
    assert captured["payload"]["options"]["top_k"] == 64


@pytest.mark.asyncio
async def test_chat_stats_computed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stats are correctly computed from Ollama response fields."""

    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        return _mock_response({"action": "water", "confidence": 0.9})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    _, stats = await ollama_client.chat(BASE_URL, MODEL, MESSAGES)
    expected_tps = _MOCK_EVAL_COUNT / _MOCK_EVAL_DURATION * 1e9
    assert stats.tokens_per_sec is not None
    assert abs(stats.tokens_per_sec - expected_tps) < 0.01
    assert stats.eval_count == _MOCK_EVAL_COUNT
    assert stats.prompt_eval_count == _MOCK_PROMPT_EVAL_COUNT
    assert stats.total_duration_ms is not None
    assert abs(stats.total_duration_ms - _MOCK_TOTAL_DURATION / 1e6) < 0.01


@pytest.mark.asyncio
async def test_chat_stats_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Ollama omits token count fields, stats fields are None."""

    async def mock_post(self, url, **kwargs):  # noqa: ARG001
        return _mock_response({"action": "water", "confidence": 0.9}, include_stats=False)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    _, stats = await ollama_client.chat(BASE_URL, MODEL, MESSAGES)
    assert stats.tokens_per_sec is None
    assert stats.eval_count is None
    assert stats.total_duration_ms is None
