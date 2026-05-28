"""Ollama tool definitions for the GrimSprout classifier agent.

Each entry is a dict in the format expected by ollama.AsyncClient.chat(tools=[...]).
"""

from __future__ import annotations

TOOL_DEFS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "water",
            "description": (
                "Record that one or more plants were watered. "
                'Pass plant_ids as a list of plant IDs, or ["all"] to water every plant in the collection.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            'List of plant IDs to water, e.g. ["calathea_01", "areca_01"]. '
                            'Use ["all"] to match every plant.'
                        ),
                    },
                },
                "required": ["plant_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fertilize",
            "description": (
                "Record that one or more plants were fertilized. "
                'Pass plant_ids as a list of plant IDs, or ["all"] for the entire collection.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'List of plant IDs to fertilize. Use ["all"] for every plant.',
                    },
                },
                "required": ["plant_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repot",
            "description": (
                "Record that one or more plants were repotted. "
                'Pass plant_ids as a list of plant IDs, or ["all"] for the entire collection.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'List of plant IDs to repot. Use ["all"] for every plant.',
                    },
                },
                "required": ["plant_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "observe",
            "description": (
                "Record a free-form observation note for a single plant. "
                "Use for health updates, symptom notes, or any non-action changelog entry."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_id": {
                        "type": "string",
                        "description": 'ID of the plant being observed, e.g. "calathea_01".',
                    },
                    "note": {
                        "type": "string",
                        "description": "Observation text in undertaker style (Russian). 1–2 sentences.",
                    },
                },
                "required": ["plant_id", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_plant_details",
            "description": (
                "Retrieve the full card of a single plant: all YAML fields plus recent changelog. "
                "Call this before answering specific questions about a plant's state, "
                "last care date, health history, or any field not visible in the summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_id": {
                        "type": "string",
                        "description": 'ID of the plant to retrieve, e.g. "calathea_01".',
                    },
                },
                "required": ["plant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plant",
            "description": (
                "Initiate creation of a new plant card. "
                "Use when the user mentions acquiring or buying a new plant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "common_name": {
                        "type": "string",
                        "description": 'Common name of the plant in Russian, e.g. "Плющ".',
                    },
                    "botanical_name": {
                        "type": "string",
                        "description": "Optional Latin botanical name.",
                    },
                },
                "required": ["common_name"],
            },
        },
    },
]

# Names of tools that write to git — used to decide whether confirmation is needed.
MUTATING_TOOLS: frozenset[str] = frozenset({"water", "fertilize", "repot", "observe"})
