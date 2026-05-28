"""IntentRouter: free-text → Agent Loop → core actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.bot.keyboards import confirm_keyboard
from grimsprout.bot.states import ActionConfirmFSM
from grimsprout.config import AppConfig
from grimsprout.db.models import Session, User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services.auth_service import requires_role
from grimsprout.services.llm import agent as llm_agent
from grimsprout.services.llm.ollama_client import LLMStats
from grimsprout.services.llm.tool_call import AgentResult, PendingMutation
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError, LLMResponseError

router = Router(name="llm_router")


def _extract_valid_history(
    sess: Session | None,
    cfg: AppConfig,
) -> list[dict[str, str]]:
    """Return recent conversation turns if within TTL, otherwise empty list."""
    if not sess or not sess.conversation_history:
        return []
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=cfg.llm.conversation_ttl_minutes)
    if sess.updated_at.replace(tzinfo=UTC) < cutoff:
        return []
    max_items = cfg.llm.conversation_history_max_turns * 2
    # Strip tool-role messages — they must not leak into next conversation
    return [
        {"role": turn.role, "content": turn.content}
        for turn in sess.conversation_history[-max_items:]
        if turn.role in ("user", "assistant")
    ]


async def _save_turn(
    db: AsyncIOMotorDatabase,
    tg_id: int,
    user_text: str,
    assistant_reply: str,
    max_items: int,
) -> None:
    """Persist a user+assistant turn to conversation history."""
    await sessions_repo.append_history(db, tg_id, "user", user_text, max_items)
    await sessions_repo.append_history(db, tg_id, "assistant", assistant_reply, max_items)


def _perf_footer(stats: LLMStats) -> str:
    """Build a one-line perf footer, e.g. ⚡ 42 tok/s · 38 tok."""
    parts: list[str] = []
    if stats.tokens_per_sec is not None:
        parts.append(f"{stats.tokens_per_sec:.0f} tok/s")
    if stats.eval_count is not None:
        parts.append(f"{stats.eval_count} tok")
    return "⚡ " + " · ".join(parts) if parts else ""


@router.message(F.text)
@requires_role("editor")
async def handle_free_text(
    message: Message,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    """Catch-all for free text: route through agent loop."""
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    repo_path = cfg.repository.require_local_path()

    sess = await sessions_repo.get(db, user.tg_id)
    history = _extract_valid_history(sess, cfg)

    try:
        result: AgentResult = await llm_agent.run(
            user_text=text,
            history=history,
            cfg=cfg,
            repo_path=repo_path,
            db=db,
            user=user,
        )
    except LLMResponseError as exc:
        logger.warning("LLM error: {}", exc)
        await message.answer("🪦 LLM не отвечает. Попробуй позже или используй прямые команды.")
        return
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked agent action: {}", exc)
        await message.answer(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\n<code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("agent action failed")
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    if result.needs_confirmation:
        # Store pending mutations serialised as JSON in FSM state
        await state.set_state(ActionConfirmFSM.waiting_llm)
        await state.update_data(
            pending_mutations=[{"tool_name": m.tool_name, "args": m.args} for m in result.pending_mutations],
            tg_id=user.tg_id,
        )
        await message.answer(result.final_reply, reply_markup=confirm_keyboard())
        return

    reply = result.final_reply
    if cfg.llm.show_perf_stats and (footer := _perf_footer(result.llm_stats)):
        reply = f"{reply}\n{footer}"
    await message.answer(reply)

    if result.pending_mutations:
        # Mutations were applied without confirmation — clear history
        await sessions_repo.clear_history(db, user.tg_id)
    else:
        # Informational answer — save to conversation history
        await _save_turn(db, user.tg_id, text, result.final_reply, cfg.llm.conversation_history_max_turns * 2)


@router.callback_query(ActionConfirmFSM.waiting_llm, F.data.in_({"action:confirm", "action:cancel"}))
@requires_role("editor")
async def llm_confirm_callback(
    callback: CallbackQuery,
    state: FSMContext,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    await callback.answer()

    if callback.data == "action:cancel":
        await state.clear()
        await callback.message.edit_text("❌ Отменено.")
        return

    data = await state.get_data()
    raw_mutations: list[dict] = data.get("pending_mutations", [])
    pending = [PendingMutation(tool_name=m["tool_name"], args=m["args"]) for m in raw_mutations]
    await state.clear()

    try:
        reply = await llm_agent.execute_pending(pending, cfg=cfg, db=db, user=user)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked confirmed action: {}", exc)
        await callback.message.edit_text(
            f"🦴 Склеп в беспорядке: в репозитории есть посторонние правки.\n<code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("confirmed action failed")
        await callback.message.edit_text(f"Ритуал прерван: <code>{exc}</code>")
        return

    await callback.message.edit_text(reply)
    await sessions_repo.clear_history(db, user.tg_id)


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
