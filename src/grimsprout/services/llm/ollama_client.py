"""Ollama HTTP client (POST /api/chat with format=json)."""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

import httpx
from loguru import logger

from grimsprout.utils.errors import LLMResponseError


@dataclasses.dataclass(frozen=True)
class LLMStats:
    """Performance statistics extracted from an Ollama response."""

    tokens_per_sec: float | None
    eval_count: int | None
    prompt_eval_count: int | None
    total_duration_ms: float | None


async def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 1.0,
    timeout_sec: int = 30,
    format_schema: dict | None = None,
    top_p: float = 0.95,
    top_k: int = 64,
) -> tuple[dict[str, Any], LLMStats]:
    """Send a chat request to Ollama and return (parsed JSON content, performance stats)."""
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "format": format_schema if format_schema is not None else "json",
        "stream": False,
        "options": {"temperature": temperature, "top_p": top_p, "top_k": top_k},
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

    eval_count: int | None = body.get("eval_count")
    eval_duration: int | None = body.get("eval_duration")
    prompt_eval_count: int | None = body.get("prompt_eval_count")
    total_duration: int | None = body.get("total_duration")

    tokens_per_sec: float | None = None
    if eval_count and eval_duration:
        tokens_per_sec = eval_count / eval_duration * 1e9

    total_duration_ms: float | None = total_duration / 1e6 if total_duration else None

    stats = LLMStats(
        tokens_per_sec=tokens_per_sec,
        eval_count=eval_count,
        prompt_eval_count=prompt_eval_count,
        total_duration_ms=total_duration_ms,
    )

    logger.debug(
        "ollama response model={} duration={:.2f}s content={}",
        model,
        duration,
        content_raw,
    )
    logger.info(
        "ollama stats model={} tokens/sec={} eval_tokens={} prompt_tokens={} total={}ms",
        model,
        f"{tokens_per_sec:.1f}" if tokens_per_sec is not None else "n/a",
        eval_count,
        prompt_eval_count,
        f"{total_duration_ms:.0f}" if total_duration_ms is not None else "n/a",
    )
    return result, stats
