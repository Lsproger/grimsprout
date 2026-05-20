"""Intent parser: JSON-string from LLM → validated pydantic model.

TODO(phase-3):
- parse(raw_json: str) -> Intent
- one retry on validation failure (caller responsibility)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["water", "fertilize", "repot", "observe", "create", "unknown"]


class Intent(BaseModel):
    target_file: str | None = None
    action: Action
    health_delta: int | None = Field(default=None, ge=-3, le=3)
    tags_add: list[str] = Field(default_factory=list)
    tags_remove: list[str] = Field(default_factory=list)
    changelog_entry: str | None = None
    needs_photo: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    clarification: str | None = None
    create_fields: dict | None = None
    reschedule_days: int | None = None


def parse(raw: str) -> Intent:
    return Intent.model_validate_json(raw)
