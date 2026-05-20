"""Ollama HTTP client (POST /api/chat with format=json).

TODO(phase-3):
- async chat(messages, model, temperature, timeout) -> raw json str
"""

from __future__ import annotations

from typing import Any


async def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    raise NotImplementedError("phase-3")
