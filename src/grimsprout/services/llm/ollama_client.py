"""Ollama async client using the official ollama-python library."""

from __future__ import annotations

import dataclasses
from typing import Any

from loguru import logger
from ollama import AsyncClient, ChatResponse, ResponseError

from grimsprout.utils.errors import LLMResponseError


@dataclasses.dataclass(frozen=True)
class LLMStats:
    """Performance statistics extracted from an Ollama response."""

    tokens_per_sec: float | None
    eval_count: int | None
    prompt_eval_count: int | None
    total_duration_ms: float | None


def _extract_stats(resp: ChatResponse) -> LLMStats:
    eval_count: int | None = getattr(resp, "eval_count", None)
    eval_duration: int | None = getattr(resp, "eval_duration", None)
    prompt_eval_count: int | None = getattr(resp, "prompt_eval_count", None)
    total_duration: int | None = getattr(resp, "total_duration", None)

    tokens_per_sec: float | None = None
    if eval_count and eval_duration:
        tokens_per_sec = eval_count / eval_duration * 1e9

    total_duration_ms: float | None = total_duration / 1e6 if total_duration else None

    return LLMStats(
        tokens_per_sec=tokens_per_sec,
        eval_count=eval_count,
        prompt_eval_count=prompt_eval_count,
        total_duration_ms=total_duration_ms,
    )


def _handle_exc(exc: Exception, timeout_sec: int) -> LLMResponseError:
    msg = str(exc)
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return LLMResponseError(f"Ollama timeout after {timeout_sec}s")
    if any(kw in msg.lower() for kw in ("connection", "connect", "refused", "network")):
        return LLMResponseError(f"Ollama connection error: {exc}")
    return LLMResponseError(f"Ollama request failed: {exc}")


async def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 1.0,
    timeout_sec: int = 30,
    top_p: float = 0.95,
    top_k: int = 64,
) -> tuple[str, LLMStats]:
    """Send a plain-text chat request (no tools) and return (content, stats).

    Used by the assistant role for free-form answers.
    """
    client = AsyncClient(host=base_url.rstrip("/"), timeout=timeout_sec)
    logger.debug("ollama chat model={} messages={}", model, len(messages))
    try:
        resp: ChatResponse = await client.chat(
            model=model,
            messages=messages,
            stream=False,
            options={"temperature": temperature, "top_p": top_p, "top_k": top_k},
        )
    except ResponseError as exc:
        raise LLMResponseError(f"Ollama error: {exc}") from exc
    except Exception as exc:
        raise _handle_exc(exc, timeout_sec) from exc

    content: str = (resp.message.content or "").strip()
    if not content:
        raise LLMResponseError("Ollama returned empty content")

    stats = _extract_stats(resp)
    logger.debug("ollama response model={} eval_count={}", model, stats.eval_count)
    return content, stats


async def chat_with_tools(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float = 1.0,
    timeout_sec: int = 30,
    top_p: float = 0.95,
    top_k: int = 64,
) -> tuple[ChatResponse, LLMStats]:
    """Send a tool-calling chat request and return (ChatResponse, stats).

    Used by the classifier role. Caller inspects resp.message.tool_calls.
    When the model decides not to call a tool, resp.message.content contains
    the natural-language response instead.
    """
    client = AsyncClient(host=base_url.rstrip("/"), timeout=timeout_sec)
    logger.debug("ollama tool-chat model={} tools={} messages={}", model, len(tools), len(messages))
    try:
        resp: ChatResponse = await client.chat(
            model=model,
            messages=messages,
            tools=tools,
            stream=False,
            options={"temperature": temperature, "top_p": top_p, "top_k": top_k},
        )
    except ResponseError as exc:
        raise LLMResponseError(f"Ollama error: {exc}") from exc
    except Exception as exc:
        raise _handle_exc(exc, timeout_sec) from exc

    stats = _extract_stats(resp)
    logger.debug(
        "ollama tool-chat response model={} tool_calls={} eval_count={}",
        model,
        len(resp.message.tool_calls or []),
        stats.eval_count,
    )
    return resp, stats
