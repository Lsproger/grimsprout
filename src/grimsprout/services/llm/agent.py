"""GrimSprout Agent Loop.

Orchestrates the two-model flow:
  1. Classifier (tool-calling model) → routes intent to tools or falls through
  2. Assistant (plain text model) → answers free-form questions

Usage::

    result = await run(
        user_text="Полил все растения",
        history=[...],
        cfg=cfg,
        repo_path=repo_path,
        db=db,
        user=user,
    )
    if result.needs_confirmation:
        # store result.pending_mutations in FSM, show preview
    else:
        # show result.final_reply to user
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.config import AppConfig
from grimsprout.core.plant_repo import build_repo_summary
from grimsprout.db.models import User
from grimsprout.services.llm import ollama_client
from grimsprout.services.llm.tool_call import AgentResult, PendingMutation
from grimsprout.services.llm.tool_executor import execute_tool
from grimsprout.services.llm.tools import MUTATING_TOOLS, TOOL_DEFS
from grimsprout.utils.errors import LLMResponseError


def _load_prompt(cfg: AppConfig, kind: str) -> str:
    """Load and return a system prompt template.

    *kind* is either ``"classifier"`` or ``"assistant"``.
    Falls back to ``system_undertaker.md`` if the new files are not configured.
    """
    if kind == "classifier":
        path = cfg.llm.classifier_prompt_file
    else:
        path = cfg.llm.assistant_prompt_file

    if path is None:
        # Graceful fallback for configs that haven't been updated yet
        fallback = cfg.llm.system_prompt_file
        if fallback and fallback.exists():
            return fallback.read_text(encoding="utf-8")
        return "You are GrimSprout, a grim plant undertaker assistant. Reply in Russian."

    return path.read_text(encoding="utf-8")


def _build_classifier_messages(
    cfg: AppConfig,
    user_text: str,
    repo_summary: str,
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prompt_template = _load_prompt(cfg, "classifier")
    system_content = prompt_template.replace("{repo_summary}", repo_summary)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    # Strip tool-role messages from history (they must not re-enter conversation)
    for turn in history:
        if turn.get("role") in ("user", "assistant"):
            messages.append(turn)
    messages.append({"role": "user", "content": user_text})
    return messages


def _build_assistant_messages(
    cfg: AppConfig,
    user_text: str,
    repo_summary: str,
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prompt_template = _load_prompt(cfg, "assistant")
    system_content = prompt_template.replace("{repo_summary}", repo_summary)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    for turn in history:
        if turn.get("role") in ("user", "assistant"):
            messages.append(turn)
    messages.append({"role": "user", "content": user_text})
    return messages


async def run(
    user_text: str,
    history: list[dict[str, Any]],
    cfg: AppConfig,
    repo_path: Path,
    db: AsyncIOMotorDatabase,
    user: User,
) -> AgentResult:
    """Run the full agent loop and return an AgentResult.

    The caller is responsible for:
    - Displaying ``result.final_reply`` to the user.
    - If ``result.needs_confirmation=True``, prompting the user and calling
      ``execute_pending(result.pending_mutations, ...)`` on confirmation.
    """
    # 1. Build fresh repo summary (no cache — always current state)
    repo_summary = build_repo_summary(repo_path)

    # 2. Classifier call (tool-calling model)
    classifier_msgs = _build_classifier_messages(cfg, user_text, repo_summary, history)
    resp, stats = await ollama_client.chat_with_tools(
        base_url=cfg.llm.base_url,
        model=cfg.llm.effective_classifier_model,
        messages=classifier_msgs,
        tools=TOOL_DEFS,
        temperature=cfg.llm.temperature,
        timeout_sec=cfg.llm.timeout_sec,
        top_p=cfg.llm.top_p,
        top_k=cfg.llm.top_k,
    )

    tool_calls = resp.message.tool_calls or []

    # 3a. No tool calls → assistant handles free-form answer
    if not tool_calls:
        text_from_classifier = (resp.message.content or "").strip()
        if text_from_classifier:
            # Classifier already gave a direct text reply (e.g. clarification question)
            return AgentResult(final_reply=text_from_classifier, llm_stats=stats)

        # Ask the assistant model for a proper answer
        assistant_msgs = _build_assistant_messages(cfg, user_text, repo_summary, history)
        try:
            assistant_reply, assistant_stats = await ollama_client.chat(
                base_url=cfg.llm.base_url,
                model=cfg.llm.effective_assistant_model,
                messages=assistant_msgs,
                temperature=cfg.llm.temperature,
                timeout_sec=cfg.llm.timeout_sec,
                top_p=cfg.llm.top_p,
                top_k=cfg.llm.top_k,
            )
        except LLMResponseError:
            raise
        return AgentResult(final_reply=assistant_reply, llm_stats=assistant_stats)

    # 3b. Tool calls present — check for read-only vs mutating
    pending: list[PendingMutation] = []
    read_results: list[str] = []

    for tc in tool_calls:
        name: str = tc.function.name
        args: dict = dict(tc.function.arguments) if tc.function.arguments else {}
        logger.debug("agent tool_call name={} args={}", name, args)

        if name not in MUTATING_TOOLS:
            # Read-only: execute immediately and feed result back to LLM
            result_str = await execute_tool(name, args, cfg=cfg, db=db, user=user)
            read_results.append(result_str)
        else:
            pending.append(PendingMutation(tool_name=name, args=args))

    # 4a. Only read-only tools were called → get final LLM answer with tool results
    if not pending:
        follow_up_msgs = list(classifier_msgs)
        follow_up_msgs.append(  # type: ignore[arg-type]
            {"role": "assistant", "content": resp.message.content or "", "tool_calls": tool_calls}
        )
        for _tc, result_str in zip(tool_calls, read_results, strict=True):
            follow_up_msgs.append({"role": "tool", "content": result_str})

        try:
            final_content, final_stats = await ollama_client.chat(
                base_url=cfg.llm.base_url,
                model=cfg.llm.effective_classifier_model,
                messages=follow_up_msgs,
                temperature=cfg.llm.temperature,
                timeout_sec=cfg.llm.timeout_sec,
                top_p=cfg.llm.top_p,
                top_k=cfg.llm.top_k,
            )
        except LLMResponseError:
            raise
        return AgentResult(final_reply=final_content, llm_stats=final_stats)

    # 4b. Mutating tools present
    if cfg.repository.confirm_commits:
        # Return pending mutations — caller must confirm before applying
        plant_ids = []
        for m in pending:
            if "plant_ids" in m.args:
                plant_ids.extend(m.args["plant_ids"])
            elif "plant_id" in m.args:
                plant_ids.append(m.args["plant_id"])

        preview = _build_pending_preview(pending)
        return AgentResult(
            final_reply=preview,
            llm_stats=stats,
            needs_confirmation=True,
            pending_mutations=pending,
        )

    # 4c. No confirmation required — apply immediately
    outputs: list[str] = []
    for mutation in pending:
        result_str = await execute_tool(mutation.tool_name, mutation.args, cfg=cfg, db=db, user=user)
        outputs.append(result_str)

    return AgentResult(
        final_reply="\n\n".join(outputs),
        llm_stats=stats,
        needs_confirmation=False,
    )


async def execute_pending(
    pending: list[PendingMutation],
    *,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> str:
    """Execute confirmed pending mutations and return combined reply."""
    outputs: list[str] = []
    for mutation in pending:
        result_str = await execute_tool(mutation.tool_name, mutation.args, cfg=cfg, db=db, user=user)
        outputs.append(result_str)
    return "\n\n".join(outputs)


def _build_pending_preview(pending: list[PendingMutation]) -> str:
    """Build a human-readable preview of pending mutations for confirmation."""
    lines = ["⏳ Подтвердить действия?"]
    for m in pending:
        tool_name = m.tool_name
        if "plant_ids" in m.args:
            ids = m.args["plant_ids"]
            if ids == ["all"]:
                lines.append(f"🌿 <b>{tool_name}</b>: все растения")
            else:
                ids_str = ", ".join(f"<code>{i}</code>" for i in ids)
                lines.append(f"🌿 <b>{tool_name}</b>: {ids_str}")
        elif "plant_id" in m.args:
            lines.append(f"🌿 <b>{tool_name}</b>: <code>{m.args['plant_id']}</code>")
            if "note" in m.args:
                lines.append(f"📋 {m.args['note']}")
    return "\n".join(lines)
