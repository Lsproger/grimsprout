"""Unit tests for grimsprout.bot.handlers.llm_router helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from grimsprout.bot.handlers.llm_router import _build_messages, _extract_valid_history
from grimsprout.db.models import ConversationTurn, Session


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


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------


def test_build_messages_no_history(monkeypatch) -> None:
    from grimsprout.bot.handlers import llm_router

    monkeypatch.setattr(llm_router, "_load_system_prompt", lambda cfg: "SYS")
    monkeypatch.setattr(
        llm_router.plant_repo,
        "list_plants",
        lambda path: [{"id": "areca_01"}, {"id": "calathea_01"}],
    )

    cfg = MagicMock()
    cfg.repository.require_local_path.return_value = "/repo"

    msgs = _build_messages(cfg, "полей арека")
    assert msgs[0] == {"role": "system", "content": "SYS"}
    # Enriched plant context: count + list
    assert "2 plant" in msgs[1]["content"]
    assert "areca_01" in msgs[1]["content"]
    assert msgs[-1] == {"role": "user", "content": "полей арека"}
    assert len(msgs) == 3


def test_build_messages_with_history(monkeypatch) -> None:
    from grimsprout.bot.handlers import llm_router

    monkeypatch.setattr(llm_router, "_load_system_prompt", lambda cfg: "SYS")
    monkeypatch.setattr(
        llm_router.plant_repo,
        "list_plants",
        lambda path: [{"id": "areca_01"}],
    )

    cfg = MagicMock()
    cfg.repository.require_local_path.return_value = "/repo"
    history = [
        {"role": "user", "content": "как ухаживать за плющом?"},
        {"role": "assistant", "content": "Укажите вид плюща."},
    ]

    msgs = _build_messages(cfg, "я не знаю, купил в икее", history=history)
    # system, system, user (history), assistant (history), user (current)
    assert len(msgs) == 5
    assert msgs[2] == {"role": "user", "content": "как ухаживать за плющом?"}
    assert msgs[3] == {"role": "assistant", "content": "Укажите вид плюща."}
    assert msgs[4] == {"role": "user", "content": "я не знаю, купил в икее"}


def test_build_messages_empty_history_same_as_no_history(monkeypatch) -> None:
    from grimsprout.bot.handlers import llm_router

    monkeypatch.setattr(llm_router, "_load_system_prompt", lambda cfg: "SYS")
    monkeypatch.setattr(llm_router.plant_repo, "list_plants", lambda path: [])

    cfg = MagicMock()
    cfg.repository.require_local_path.return_value = "/repo"

    assert _build_messages(cfg, "test") == _build_messages(cfg, "test", history=[])
