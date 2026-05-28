"""Unit tests for grimsprout.bot.handlers.llm_router helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from grimsprout.bot.handlers.llm_router import _extract_valid_history, _perf_footer
from grimsprout.db.models import ConversationTurn, Session
from grimsprout.services.llm.ollama_client import LLMStats


def _make_session(
    history: list[tuple[str, str]] | None = None,
    updated_at: datetime | None = None,
) -> Session:
    turns = [ConversationTurn(role=r, content=c) for r, c in (history or [])]
    return Session(
        tg_id=1,
        conversation_history=turns,
        updated_at=updated_at or datetime.now(tz=UTC),
    )


def _make_cfg(max_turns: int = 5, ttl_minutes: int = 30) -> MagicMock:
    cfg = MagicMock()
    cfg.llm.conversation_history_max_turns = max_turns
    cfg.llm.conversation_ttl_minutes = ttl_minutes
    return cfg


# ---------------------------------------------------------------------------
# _extract_valid_history
# ---------------------------------------------------------------------------


def test_extract_valid_history_no_session() -> None:
    cfg = _make_cfg()
    assert _extract_valid_history(None, cfg) == []


def test_extract_valid_history_empty_history() -> None:
    cfg = _make_cfg()
    sess = _make_session()
    assert _extract_valid_history(sess, cfg) == []


def test_extract_valid_history_within_ttl() -> None:
    cfg = _make_cfg(max_turns=5, ttl_minutes=30)
    sess = _make_session(
        history=[("user", "hello"), ("assistant", "hi")],
        updated_at=datetime.now(tz=UTC) - timedelta(minutes=10),
    )
    result = _extract_valid_history(sess, cfg)
    assert result == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_extract_valid_history_stale_returns_empty() -> None:
    cfg = _make_cfg(ttl_minutes=30)
    sess = _make_session(
        history=[("user", "old message"), ("assistant", "old reply")],
        updated_at=datetime.now(tz=UTC) - timedelta(minutes=31),
    )
    assert _extract_valid_history(sess, cfg) == []


def test_extract_valid_history_trims_to_max_turns() -> None:
    cfg = _make_cfg(max_turns=2)  # keeps 2*2=4 messages
    pairs = [(r, f"msg{i}") for i in range(6) for r in ("user", "assistant")]  # 12 messages
    sess = _make_session(history=pairs, updated_at=datetime.now(tz=UTC))
    result = _extract_valid_history(sess, cfg)
    assert len(result) == 4
    # Last 4 entries of 12
    assert result[-1]["content"] == "msg5"


def test_extract_valid_history_strips_tool_role() -> None:
    """Only user/assistant turns should be returned (ConversationTurn enforces this at storage level)."""
    cfg = _make_cfg(max_turns=5, ttl_minutes=30)
    sess = _make_session(
        history=[
            ("user", "полей все"),
            ("assistant", "подтверди"),
        ],
        updated_at=datetime.now(tz=UTC),
    )
    result = _extract_valid_history(sess, cfg)
    assert all(t["role"] in ("user", "assistant") for t in result)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _perf_footer
# ---------------------------------------------------------------------------


def test_perf_footer_full() -> None:
    stats = LLMStats(tokens_per_sec=42.7, eval_count=38, prompt_eval_count=26, total_duration_ms=1300.0)
    footer = _perf_footer(stats)
    assert "43 tok/s" in footer
    assert "38 tok" in footer
    assert footer.startswith("⚡")


def test_perf_footer_no_stats() -> None:
    stats = LLMStats(tokens_per_sec=None, eval_count=None, prompt_eval_count=None, total_duration_ms=None)
    assert _perf_footer(stats) == ""
