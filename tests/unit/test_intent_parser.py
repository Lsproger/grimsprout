"""Tests for grimsprout.services.llm.intent_parser."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from grimsprout.services.llm.intent_parser import parse


def _make_raw(**kwargs) -> str:
    base = {"action": "water", "confidence": 0.9}
    base.update(kwargs)
    return json.dumps(base)


def test_parse_water() -> None:
    raw = _make_raw(action="water", confidence=0.95)
    intent = parse(raw)
    assert intent.action == "water"
    assert intent.confidence == 0.95


def test_parse_query_action() -> None:
    """'query' action: answer field carries the LLM's response text."""
    raw = _make_raw(action="query", confidence=0.9, answer="У вас 5 растений.")
    intent = parse(raw)
    assert intent.action == "query"
    assert intent.answer == "У вас 5 растений."
    assert intent.clarification is None
    assert intent.target_file is None


def test_parse_all_actions_accepted() -> None:
    for action in ("water", "fertilize", "repot", "observe", "create", "query", "unknown"):
        intent = parse(_make_raw(action=action))
        assert intent.action == action


def test_parse_invalid_action_rejected() -> None:
    with pytest.raises(ValidationError):
        parse(_make_raw(action="dance"))


def test_parse_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        parse(json.dumps({"action": "water"}))  # confidence is required


def test_parse_health_delta_bounds() -> None:
    intent = parse(_make_raw(health_delta=3))
    assert intent.health_delta == 3

    with pytest.raises(ValidationError):
        parse(_make_raw(health_delta=4))  # max is 3

    with pytest.raises(ValidationError):
        parse(_make_raw(health_delta=-4))  # min is -3


def test_parse_answer_field_present() -> None:
    """answer field is accepted and distinct from clarification."""
    raw = _make_raw(action="query", confidence=0.9, answer="Ответ на вопрос.", clarification=None)
    intent = parse(raw)
    assert intent.answer == "Ответ на вопрос."
    assert intent.clarification is None


def test_parse_clarification_for_low_confidence_action() -> None:
    """clarification is a question to the user when intent is ambiguous."""
    raw = _make_raw(action="water", confidence=0.3, clarification="Какое растение полить?", answer=None)
    intent = parse(raw)
    assert intent.clarification == "Какое растение полить?"
    assert intent.answer is None
    assert intent.confidence < 0.5
