"""PhotoAnalyzer abstraction + Stub. Real implementation deferred."""
from __future__ import annotations

from typing import Protocol


class PhotoAnalyzer(Protocol):
    async def analyze(self, image_bytes: bytes) -> dict:
        """Return a free-form dict describing observed health signals."""


class StubAnalyzer:
    async def analyze(self, image_bytes: bytes) -> dict:
        return {"available": False, "note": "PhotoAnalyzer stub"}
