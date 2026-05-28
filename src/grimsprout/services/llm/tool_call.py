"""Data models for the agent loop results.

Replaces the old Intent / intent_parser.py approach.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from grimsprout.services.llm.ollama_client import LLMStats


@dataclasses.dataclass
class PendingMutation:
    """A single tool call that has been approved for execution but not yet applied."""

    tool_name: str
    args: dict[str, Any]


@dataclasses.dataclass
class AgentResult:
    """Final result produced by the agent loop.

    Exactly one of ``final_reply`` or ``pending_mutations`` (non-empty) will be
    meaningful at a time:

    - ``needs_confirmation=False``: mutations have already been applied, or the
      turn was purely informational. ``final_reply`` holds the text to show the user.
    - ``needs_confirmation=True``: mutations are pending. The bot should show a
      confirmation prompt; on approval, call the tool executor for each item in
      ``pending_mutations``. ``final_reply`` holds the preview text.
    """

    final_reply: str
    llm_stats: LLMStats
    needs_confirmation: bool = False
    pending_mutations: list[PendingMutation] = dataclasses.field(default_factory=list)

    def pending_plant_ids(self) -> list[str]:
        """Flat list of all plant IDs across pending mutations (for preview)."""
        ids: list[str] = []
        for m in self.pending_mutations:
            if "plant_ids" in m.args:
                ids.extend(m.args["plant_ids"])
            elif "plant_id" in m.args:
                ids.append(m.args["plant_id"])
        return ids
