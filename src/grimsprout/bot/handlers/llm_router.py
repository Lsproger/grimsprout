"""IntentRouter: free-text → LLM → core actions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from aiogram import Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from grimsprout.bot.keyboards import confirm_keyboard
from grimsprout.bot.states import ActionConfirmFSM
from grimsprout.config import AppConfig
from grimsprout.core import changelog, md_parser, plant_repo
from grimsprout.db.models import Session, User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.services.llm import ollama_client
from grimsprout.services.llm.intent_parser import Intent, parse
from grimsprout.services.llm.ollama_client import LLMStats
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError, LLMResponseError

router = Router(name="llm_router")

RETRY_MSG = {
    "role": "system",
    "content": "Ответ должен быть СТРОГО валидный JSON по схеме. Без markdown, без комментариев.",
}

DATE_FIELDS: dict[str, str] = {
    "water": "last_watered_date",
    "fertilize": "last_fertilized_date",
    "repot": "last_repot_date",
}

_MUTATING_ACTIONS: frozenset[str] = frozenset({"water", "fertilize", "repot"})
_LLM_CONFIRM_ACTIONS: frozenset[str] = frozenset({"water", "fertilize", "repot", "observe"})

_cached_system_prompt: str | None = None
_cached_intent_schema: dict | None = None


def _load_intent_schema(cfg: AppConfig) -> dict:
    global _cached_intent_schema  # noqa: PLW0603
    if _cached_intent_schema is None:
        _cached_intent_schema = json.loads(cfg.llm.intent_schema_file.read_text(encoding="utf-8"))
    return _cached_intent_schema


def _load_system_prompt(cfg: AppConfig) -> str:
    global _cached_system_prompt  # noqa: PLW0603
    if _cached_system_prompt is None:
        template = cfg.llm.system_prompt_file.read_text(encoding="utf-8")
        schema = cfg.llm.intent_schema_file.read_text(encoding="utf-8")
        _cached_system_prompt = template.replace("{schema}", schema)
    return _cached_system_prompt


def _build_messages(
    cfg: AppConfig,
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    system_prompt = _load_system_prompt(cfg)
    repo_path = cfg.repository.require_local_path()
    plants = plant_repo.list_plants(repo_path)
    plant_ids = ", ".join(p["id"] for p in plants)
    plant_count = len(plants)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": (
                f"The user has {plant_count} plant(s) registered: {plant_ids}. "
                "Use this list when answering questions about the collection."
            ),
        },
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    return messages


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
    return [{"role": turn.role, "content": turn.content} for turn in sess.conversation_history[-max_items:]]


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


async def _resolve_plant_from_intent(
    repo_path: Path,
    db: AsyncIOMotorDatabase,
    tg_id: int,
    target_file: str | None,
) -> str | None:
    """Resolve plant_id from intent target_file or session."""
    if target_file:
        path = plant_repo.find(repo_path, target_file)
        if path:
            return path.stem
        return None
    sess = await sessions_repo.get(db, tg_id)
    if sess and sess.current_plant_id:
        return sess.current_plant_id
    return None


async def _call_llm(cfg: AppConfig, messages: list[dict[str, str]]) -> tuple[Intent, LLMStats]:
    """Call LLM and parse intent, with one retry on parse failure."""
    schema = _load_intent_schema(cfg)
    raw, stats = await ollama_client.chat(
        cfg.llm.base_url,
        cfg.llm.model,
        messages,
        cfg.llm.temperature,
        cfg.llm.timeout_sec,
        format_schema=schema,
        top_p=cfg.llm.top_p,
        top_k=cfg.llm.top_k,
    )
    raw_str = raw if isinstance(raw, str) else json.dumps(raw)
    try:
        return parse(raw_str), stats
    except ValidationError:
        # One retry with format reminder
        messages_retry = [*messages, RETRY_MSG]
        raw2, stats2 = await ollama_client.chat(
            cfg.llm.base_url,
            cfg.llm.model,
            messages_retry,
            cfg.llm.temperature,
            cfg.llm.timeout_sec,
            format_schema=schema,
            top_p=cfg.llm.top_p,
            top_k=cfg.llm.top_k,
        )
        raw_str2 = raw2 if isinstance(raw2, str) else json.dumps(raw2)
        return parse(raw_str2), stats2  # raise if still invalid


async def _apply_intent(
    intent: Intent,
    plant_id: str,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> str:
    """Apply intent to plant card. Returns formatted reply text."""
    repo_path = cfg.repository.require_local_path()
    path = repo_path / f"{plant_id}.md"

    today = date.today()
    yaml_data, _ = md_parser.read(path)
    changes: list[str] = []

    # 1. Date field for water/fertilize/repot
    if intent.action in DATE_FIELDS:
        field = DATE_FIELDS[intent.action]
        md_parser.update_yaml(path, {field: today.isoformat()})
        changes.append(f"<code>{field}</code> = <code>{today.isoformat()}</code>")

    # 2. Health delta
    if intent.health_delta is not None and intent.health_delta != 0:
        current = float(yaml_data.get("health_score", 5.0) or 5.0)
        new_score = max(1.0, min(10.0, current + intent.health_delta))
        md_parser.update_yaml(path, {"health_score": new_score})
        changes.append(f"❤️ Здоровье: {current} → {new_score}")

    # 3. Tags
    if intent.tags_add or intent.tags_remove:
        current_tags: list[str] = yaml_data.get("tags", []) or []
        new_tags = [t for t in current_tags if t not in intent.tags_remove]
        for t in intent.tags_add:
            if t not in new_tags:
                new_tags.append(t)
        md_parser.update_yaml(path, {"tags": new_tags})
        changes.append(f"🏷 Теги: {', '.join(new_tags)}")

    # 4. Changelog entry
    if intent.changelog_entry:
        changelog.append_entry(path, today, intent.changelog_entry)

    # 5. Git commit
    git_service.add(repo_path, [path])
    sha = git_service.commit(
        repo_path,
        f"chore(auto): {intent.action} {plant_id}\n\n"
        f"{intent.changelog_entry or intent.action}\n"
        f"GrimSprout: tg_id={user.tg_id}, llm={cfg.llm.model}",
    )

    # 6. Audit
    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action=f"llm:{intent.action}",
        payload={"plant_id": plant_id, "confidence": intent.confidence},
        file=f"{plant_id}.md",
        commit_sha=sha,
    )

    # Build reply
    parts = [f"✅ <code>{plant_id}</code>: {intent.changelog_entry or intent.action}"]
    parts.extend(changes)
    parts.append(f"Коммит: <code>{sha[:10]}</code>")
    return "\n".join(parts)


def _perf_footer(stats: LLMStats) -> str:
    """Build a one-line perf footer for chat replies, e.g. ⚡ 42 tok/s · 38 tok."""
    parts: list[str] = []
    if stats.tokens_per_sec is not None:
        parts.append(f"{stats.tokens_per_sec:.0f} tok/s")
    if stats.eval_count is not None:
        parts.append(f"{stats.eval_count} tok")
    return "⚡ " + " · ".join(parts) if parts else ""


def _build_llm_preview(intent: Intent, plant_id: str) -> str:
    """Build a confirmation preview message for LLM-triggered actions."""
    today = date.today()
    lines = [
        "⏳ Подтвердить действие?",
        f"🌿 Растение: <code>{plant_id}</code>",
        f"🤖 {intent.action} (LLM, {intent.confidence:.0%})",
    ]
    if intent.changelog_entry:
        lines.append(f"📋 {intent.changelog_entry}")
    if intent.action in DATE_FIELDS:
        lines.append(f"📅 Дата: <code>{today.isoformat()}</code>")
    return "\n".join(lines)


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
    """Catch-all for free text: route through LLM."""
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    repo_path = cfg.repository.require_local_path()

    # Load session once — reused for history extraction and plant resolution
    sess = await sessions_repo.get(db, user.tg_id)
    history = _extract_valid_history(sess, cfg)

    # Call LLM with conversation history injected
    messages = _build_messages(cfg, text, history=history)
    try:
        intent, llm_stats = await _call_llm(cfg, messages)
    except LLMResponseError as exc:
        logger.warning("LLM error: {}", exc)
        await message.answer("🪦 LLM не отвечает. Попробуй позже или используй прямые команды.")
        return
    except ValidationError:
        await message.answer(
            "Не удалось распознать намерение. Попробуй переформулировать или используй команды."
        )
        return

    # 006: action-specific confidence threshold
    threshold = (
        cfg.llm.mutate_confidence_threshold
        if intent.action in _MUTATING_ACTIONS
        else cfg.llm.confidence_threshold
    )
    if intent.confidence < threshold or intent.clarification:
        reply = intent.clarification or "Не совсем понял. Уточни, что именно нужно сделать."
        await message.answer(reply)
        await _save_turn(db, user.tg_id, text, reply, cfg.llm.conversation_history_max_turns * 2)
        return

    # 004: informational query — return LLM's answer without touching git
    if intent.action == "query":
        reply = intent.answer or intent.clarification or "Не знаю ответа. Попробуй /plants или /help."
        if cfg.llm.show_perf_stats and (footer := _perf_footer(llm_stats)):
            reply = f"{reply}\n{footer}"
        await message.answer(reply)
        await _save_turn(db, user.tg_id, text, reply, cfg.llm.conversation_history_max_turns * 2)
        return

    # Unknown action
    if intent.action == "unknown":
        reply = "Не распознал действие. Попробуй:\n/water — полив\n/fertilize — удобрение\n/repot — пересадка"
        await message.answer(reply)
        await _save_turn(db, user.tg_id, text, reply, cfg.llm.conversation_history_max_turns * 2)
        return

    # Create deferred to /new
    if intent.action == "create":
        await message.answer("Для создания карточки используй /new.")
        return

    # Resolve plant (uses target_file from intent, falls back to session)
    plant_id = await _resolve_plant_from_intent(repo_path, db, user.tg_id, intent.target_file)
    if not plant_id:
        reply = (
            f"Не нашёл растение «{intent.target_file}». Выбери через /plants."
            if intent.target_file
            else "Сначала выбери растение через /plants."
        )
        await message.answer(reply)
        await _save_turn(db, user.tg_id, text, reply, cfg.llm.conversation_history_max_turns * 2)
        return

    # Verify file exists
    path = repo_path / f"{plant_id}.md"
    if not path.exists():
        await message.answer(f"Файл карточки <code>{plant_id}.md</code> не найден.")
        return

    # 005: confirm gate for LLM-mutating actions
    if cfg.repository.confirm_commits and intent.action in _LLM_CONFIRM_ACTIONS:
        await state.set_state(ActionConfirmFSM.waiting_llm)
        await state.update_data(
            intent_data=intent.model_dump(mode="json"),
            plant_id=plant_id,
            tg_id=user.tg_id,
        )
        await message.answer(_build_llm_preview(intent, plant_id), reply_markup=confirm_keyboard())
        return

    # Apply intent
    try:
        reply = await _apply_intent(intent, plant_id, cfg, db, user)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked LLM action: {}", exc)
        await message.answer(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\n<code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("LLM action failed")
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    if cfg.llm.show_perf_stats and (footer := _perf_footer(llm_stats)):
        reply = f"{reply}\n{footer}"
    await message.answer(reply)
    # Successful action: clear history so next conversation starts fresh
    await sessions_repo.clear_history(db, user.tg_id)


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
    intent = Intent.model_validate(data["intent_data"])
    plant_id = data["plant_id"]
    await state.clear()

    try:
        reply = await _apply_intent(intent, plant_id, cfg, db, user)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked LLM action: {}", exc)
        await callback.message.edit_text(
            f"🦴 Склеп в беспорядке: в репозитории есть посторонние правки.\n<code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("LLM action failed")
        await callback.message.edit_text(f"Ритуал прерван: <code>{exc}</code>")
        return

    await callback.message.edit_text(reply)
    await sessions_repo.clear_history(db, user.tg_id)


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
