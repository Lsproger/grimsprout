"""Unit tests for grimsprout.services.llm.agent."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grimsprout.services.llm import agent as llm_agent
from grimsprout.services.llm.ollama_client import LLMStats
from grimsprout.services.llm.tool_call import AgentResult, PendingMutation

_DUMMY_STATS = LLMStats(tokens_per_sec=40.0, eval_count=30, prompt_eval_count=10, total_duration_ms=800.0)


def _make_cfg(repo_path: Path, confirm_commits: bool = False) -> MagicMock:
    cfg = MagicMock()
    cfg.repository.require_local_path.return_value = repo_path
    cfg.repository.confirm_commits = confirm_commits
    cfg.llm.base_url = "http://localhost:11434"
    cfg.llm.effective_classifier_model = "test-model"
    cfg.llm.effective_assistant_model = "test-model"
    cfg.llm.temperature = 0.5
    cfg.llm.timeout_sec = 30
    cfg.llm.top_p = 0.95
    cfg.llm.top_k = 64
    cfg.llm.classifier_prompt_file = None
    cfg.llm.assistant_prompt_file = None
    cfg.llm.system_prompt_file = None
    return cfg


def _make_user() -> MagicMock:
    user = MagicMock()
    user.tg_id = 42
    return user


def _make_classifier_resp(content: str = "", tool_calls=None) -> MagicMock:
    resp = MagicMock()
    resp.message.content = content
    resp.message.tool_calls = tool_calls
    return resp


def _make_tool_call(name: str, arguments: dict) -> MagicMock:
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


# ---------------------------------------------------------------------------
# No tool calls — falls through to assistant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_no_tool_calls_goes_to_assistant(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    classifier_resp = _make_classifier_resp(content="")

    with (
        patch(
            "grimsprout.services.llm.agent.ollama_client.chat_with_tools", new_callable=AsyncMock
        ) as mock_cls,
        patch("grimsprout.services.llm.agent.ollama_client.chat", new_callable=AsyncMock) as mock_ast,
    ):
        mock_cls.return_value = (classifier_resp, _DUMMY_STATS)
        mock_ast.return_value = ("Ответ ассистента.", _DUMMY_STATS)

        result = await llm_agent.run("Как дела?", [], cfg=cfg, repo_path=tmp_trava, db=db, user=user)

    assert isinstance(result, AgentResult)
    assert result.final_reply == "Ответ ассистента."
    assert not result.needs_confirmation
    mock_ast.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_classifier_direct_reply(tmp_trava: Path) -> None:
    """Classifier returns a plain text reply (e.g. clarification) — no assistant call."""
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    classifier_resp = _make_classifier_resp(content="Уточни, какое именно растение полить.")

    with (
        patch(
            "grimsprout.services.llm.agent.ollama_client.chat_with_tools", new_callable=AsyncMock
        ) as mock_cls,
        patch("grimsprout.services.llm.agent.ollama_client.chat", new_callable=AsyncMock) as mock_ast,
    ):
        mock_cls.return_value = (classifier_resp, _DUMMY_STATS)

        result = await llm_agent.run("полей", [], cfg=cfg, repo_path=tmp_trava, db=db, user=user)

    assert result.final_reply == "Уточни, какое именно растение полить."
    mock_ast.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tool calls with confirm_commits=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_mutating_with_confirm(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava, confirm_commits=True)
    user = _make_user()
    db = AsyncMock()

    tc = _make_tool_call("water", {"plant_ids": ["areca_01"]})
    classifier_resp = _make_classifier_resp(tool_calls=[tc])

    with patch(
        "grimsprout.services.llm.agent.ollama_client.chat_with_tools", new_callable=AsyncMock
    ) as mock_cls:
        mock_cls.return_value = (classifier_resp, _DUMMY_STATS)

        result = await llm_agent.run("полей арека", [], cfg=cfg, repo_path=tmp_trava, db=db, user=user)

    assert result.needs_confirmation is True
    assert len(result.pending_mutations) == 1
    assert result.pending_mutations[0].tool_name == "water"
    assert "areca_01" in result.final_reply or "water" in result.final_reply


# ---------------------------------------------------------------------------
# Tool calls without confirmation — execute immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_mutating_without_confirm(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava, confirm_commits=False)
    user = _make_user()
    db = AsyncMock()

    tc = _make_tool_call("water", {"plant_ids": ["areca_01"]})
    classifier_resp = _make_classifier_resp(tool_calls=[tc])

    with (
        patch(
            "grimsprout.services.llm.agent.ollama_client.chat_with_tools", new_callable=AsyncMock
        ) as mock_cls,
        patch("grimsprout.services.llm.agent.execute_tool", new_callable=AsyncMock) as mock_exec,
    ):
        mock_cls.return_value = (classifier_resp, _DUMMY_STATS)
        mock_exec.return_value = "✅ areca_01 (abc12345)"

        result = await llm_agent.run("полей арека", [], cfg=cfg, repo_path=tmp_trava, db=db, user=user)

    assert result.needs_confirmation is False
    assert "areca_01" in result.final_reply
    mock_exec.assert_awaited_once()


# ---------------------------------------------------------------------------
# Read-only tool calls (get_plant_details) — feed back to LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_readonly_tool_feeds_result_back(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    tc = _make_tool_call("get_plant_details", {"plant_id": "areca_01"})
    classifier_resp = _make_classifier_resp(content="", tool_calls=[tc])

    with (
        patch(
            "grimsprout.services.llm.agent.ollama_client.chat_with_tools", new_callable=AsyncMock
        ) as mock_cls,
        patch("grimsprout.services.llm.agent.execute_tool", new_callable=AsyncMock) as mock_exec,
        patch("grimsprout.services.llm.agent.ollama_client.chat", new_callable=AsyncMock) as mock_chat,
    ):
        mock_cls.return_value = (classifier_resp, _DUMMY_STATS)
        mock_exec.return_value = "id: areca_01\nstatus: alive\n..."
        mock_chat.return_value = ("Арека здорова.", _DUMMY_STATS)

        result = await llm_agent.run("Как дела у ареки?", [], cfg=cfg, repo_path=tmp_trava, db=db, user=user)

    assert result.final_reply == "Арека здорова."
    mock_exec.assert_awaited_once()
    mock_chat.assert_awaited_once()


# ---------------------------------------------------------------------------
# execute_pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_pending(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    pending = [
        PendingMutation(tool_name="water", args={"plant_ids": ["areca_01"]}),
        PendingMutation(tool_name="water", args={"plant_ids": ["calathea_01"]}),
    ]

    with patch("grimsprout.services.llm.agent.execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = ["✅ areca_01", "✅ calathea_01"]
        reply = await llm_agent.execute_pending(pending, cfg=cfg, db=db, user=user)

    assert "areca_01" in reply
    assert "calathea_01" in reply
    assert mock_exec.await_count == 2


# ---------------------------------------------------------------------------
# _build_pending_preview
# ---------------------------------------------------------------------------


def test_build_pending_preview_batch() -> None:
    pending = [PendingMutation(tool_name="water", args={"plant_ids": ["areca_01", "calathea_01"]})]
    preview = llm_agent._build_pending_preview(pending)
    assert "water" in preview
    assert "areca_01" in preview
    assert "calathea_01" in preview


def test_build_pending_preview_all() -> None:
    pending = [PendingMutation(tool_name="fertilize", args={"plant_ids": ["all"]})]
    preview = llm_agent._build_pending_preview(pending)
    assert "все растения" in preview


# ---------------------------------------------------------------------------
# AgentResult helpers
# ---------------------------------------------------------------------------


def test_agent_result_pending_plant_ids() -> None:
    result = AgentResult(
        final_reply="preview",
        llm_stats=_DUMMY_STATS,
        needs_confirmation=True,
        pending_mutations=[
            PendingMutation("water", {"plant_ids": ["areca_01", "calathea_01"]}),
            PendingMutation("observe", {"plant_id": "dracaena_01", "note": "test"}),
        ],
    )
    ids = result.pending_plant_ids()
    assert "areca_01" in ids
    assert "calathea_01" in ids
    assert "dracaena_01" in ids
