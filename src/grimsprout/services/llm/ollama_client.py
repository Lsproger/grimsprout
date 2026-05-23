"""Ollama HTTP client (POST /api/chat with format=json)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from loguru import logger

from grimsprout.utils.errors import LLMResponseError


async def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """Send a chat request to Ollama and return parsed JSON content."""
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }

    t0 = time.monotonic()
    logger.debug(
        "ollama request model={} messages={} temperature={}",
        model,
        json.dumps(messages, ensure_ascii=False),
        temperature,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMResponseError(f"Ollama timeout after {timeout_sec}s") from exc
    except httpx.HTTPStatusError as exc:
        raise LLMResponseError(f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise LLMResponseError(f"Ollama connection error: {exc}") from exc

    duration = time.monotonic() - t0

    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMResponseError("Ollama returned non-JSON response") from exc

    content_raw = body.get("message", {}).get("content", "")
    if not content_raw:
        raise LLMResponseError("Ollama returned empty content")

    try:
        result = json.loads(content_raw)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"Invalid JSON from LLM: {content_raw[:200]}") from exc

    logger.debug(
        "ollama response model={} duration={:.2f}s content={}",
        model,
        duration,
        content_raw,
    )
    return result
