"""IntentRouter: free-text → LLM → core actions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from aiogram import Dispatcher, F, Router
from aiogram.types import Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from grimsprout.config import AppConfig
from grimsprout.core import changelog, md_parser, plant_repo
from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.services.llm import ollama_client
from grimsprout.services.llm.intent_parser import Intent, parse
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

_cached_system_prompt: str | None = None


def _load_system_prompt(cfg: AppConfig) -> str:
    global _cached_system_prompt  # noqa: PLW0603
    if _cached_system_prompt is None:
        template = cfg.llm.system_prompt_file.read_text(encoding="utf-8")
        schema = cfg.llm.intent_schema_file.read_text(encoding="utf-8")
        _cached_system_prompt = template.replace("{schema}", schema)
    return _cached_system_prompt


def _build_messages(cfg: AppConfig, user_text: str) -> list[dict[str, str]]:
    system_prompt = _load_system_prompt(cfg)
    repo_path = cfg.repository.require_local_path()
    plants = plant_repo.list_plants(repo_path)
    plant_ids = ", ".join(p["id"] for p in plants)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Известные растения: {plant_ids}"},
        {"role": "user", "content": user_text},
    ]


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


async def _call_llm(cfg: AppConfig, messages: list[dict[str, str]]) -> Intent:
    """Call LLM and parse intent, with one retry on parse failure."""
    raw = await ollama_client.chat(
        cfg.llm.base_url,
        cfg.llm.model,
        messages,
        cfg.llm.temperature,
        cfg.llm.timeout_sec,
    )
    raw_str = raw if isinstance(raw, str) else __import__("json").dumps(raw)
    try:
        return parse(raw_str)
    except ValidationError:
        # One retry with format reminder
        messages_retry = [*messages, RETRY_MSG]
        raw2 = await ollama_client.chat(
            cfg.llm.base_url,
            cfg.llm.model,
            messages_retry,
            cfg.llm.temperature,
            cfg.llm.timeout_sec,
        )
        raw_str2 = raw2 if isinstance(raw2, str) else __import__("json").dumps(raw2)
        return parse(raw_str2)  # raise if still invalid


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


@router.message(F.text)
@requires_role("editor")
async def handle_free_text(
    message: Message,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    """Catch-all for free text: route through LLM."""
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    repo_path = cfg.repository.require_local_path()

    # Call LLM
    messages = _build_messages(cfg, text)
    try:
        intent = await _call_llm(cfg, messages)
    except LLMResponseError as exc:
        logger.warning("LLM error: {}", exc)
        await message.answer("🪦 LLM не отвечает. Попробуй позже или используй прямые команды.")
        return
    except ValidationError:
        await message.answer(
            "Не удалось распознать намерение. Попробуй переформулировать или используй команды."
        )
        return

    # Low confidence or clarification needed
    if intent.confidence < 0.5 or intent.clarification:
        reply = intent.clarification or "Не совсем понял. Уточни, что именно нужно сделать."
        await message.answer(reply)
        return

    # Unknown action
    if intent.action == "unknown":
        await message.answer(
            "Не распознал действие. Попробуй:\n/water — полив\n/fertilize — удобрение\n/repot — пересадка"
        )
        return

    # Create deferred to /new
    if intent.action == "create":
        await message.answer("Для создания карточки используй /new.")
        return

    # Resolve plant
    plant_id = await _resolve_plant_from_intent(repo_path, db, user.tg_id, intent.target_file)
    if not plant_id:
        if intent.target_file:
            await message.answer(f"Не нашёл растение «{intent.target_file}». Выбери через /plants.")
        else:
            await message.answer("Сначала выбери растение через /plants.")
        return

    # Verify file exists
    path = repo_path / f"{plant_id}.md"
    if not path.exists():
        await message.answer(f"Файл карточки <code>{plant_id}.md</code> не найден.")
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

    await message.answer(reply)


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
