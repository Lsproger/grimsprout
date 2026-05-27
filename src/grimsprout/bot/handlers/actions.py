"""Direct commands: /water, /fertilize, /repot.

Resolution order for the target plant:
1. Command argument (e.g. `/water calathea_01` or `/water Калатея`)
2. `sessions.current_plant_id` of the user

On success: updates YAML date field, appends a changelog entry, stages and
commits the .md file in the trava repo. Photo handling is out of scope here.
"""

from __future__ import annotations

from datetime import date

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.bot.keyboards import confirm_keyboard
from grimsprout.bot.states import ActionConfirmFSM
from grimsprout.config import AppConfig
from grimsprout.core import changelog, md_parser, plant_repo
from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError

router = Router(name="actions")


ACTIONS: dict[str, tuple[str, str]] = {
    "water": ("last_watered_date", "Полив выполнен."),
    "fertilize": ("last_fertilized_date", "Удобрение внесено."),
    "repot": ("last_repot_date", "Пересадка зафиксирована."),
}


async def _resolve_plant_id(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    tg_id: int,
) -> str | None:
    arg = (command.args or "").strip()
    if arg:
        path = plant_repo.find(cfg.repository.require_local_path(), arg)
        if path is None:
            await message.answer(f"Не нашёл растения по запросу: <code>{arg}</code>. Попробуй /plants.")
            return None
        return path.stem

    sess = await sessions_repo.get(db, tg_id)
    if sess and sess.current_plant_id:
        return sess.current_plant_id

    await message.answer("Сначала выбери растение через /plants или укажи id аргументом.")
    return None


def _compute_action(*, plant_id: str, action: str, tg_id: int) -> dict:
    """Build a serialisable payload describing the action without touching any files."""
    field, action_text = ACTIONS[action]
    today = date.today()
    return {
        "plant_id": plant_id,
        "action": action,
        "field": field,
        "new_value": today.isoformat(),
        "commit_msg": (f"chore(auto): {action} {plant_id}\n\n{action_text}\nGrimSprout: tg_id={tg_id}"),
        "action_text": action_text,
        "tg_id": tg_id,
    }


async def _execute_action(payload: dict, *, cfg: AppConfig, db: AsyncIOMotorDatabase) -> str:
    """Apply changes to the plant card, commit and record audit. Returns commit SHA."""
    repo_path = cfg.repository.require_local_path()
    path = repo_path / f"{payload['plant_id']}.md"
    md_parser.update_yaml(path, {payload["field"]: payload["new_value"]})
    changelog.append_entry(path, date.fromisoformat(payload["new_value"]), payload["action_text"])
    git_service.add(repo_path, [path])
    sha = git_service.commit(repo_path, payload["commit_msg"])
    await audit_svc.record(
        db,
        tg_id=payload["tg_id"],
        action=payload["action"],
        payload={"plant_id": payload["plant_id"]},
        file=f"{payload['plant_id']}.md",
        commit_sha=sha,
    )
    return sha


async def _execute_note(payload: dict, *, cfg: AppConfig, db: AsyncIOMotorDatabase) -> str:
    """Append a free-text note to the plant changelog and commit. Returns commit SHA."""
    repo_path = cfg.repository.require_local_path()
    path = repo_path / f"{payload['plant_id']}.md"
    changelog.append_entry(path, date.fromisoformat(payload["new_value"]), payload["note_text"])
    git_service.add(repo_path, [path])
    sha = git_service.commit(repo_path, payload["commit_msg"])
    await audit_svc.record(
        db,
        tg_id=payload["tg_id"],
        action="note",
        payload={"plant_id": payload["plant_id"]},
        file=f"{payload['plant_id']}.md",
        commit_sha=sha,
    )
    return sha


async def _apply_action(
    message: Message,
    command: CommandObject,
    *,
    action: str,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
) -> None:
    plant_id = await _resolve_plant_id(message, command, cfg, db, user.tg_id)
    if plant_id is None:
        return

    path = cfg.repository.require_local_path() / f"{plant_id}.md"
    if not path.exists():
        await message.answer(f"Файл карточки <code>{plant_id}.md</code> не найден.")
        return

    payload = _compute_action(plant_id=plant_id, action=action, tg_id=user.tg_id)

    if cfg.repository.confirm_commits:
        await state.set_state(ActionConfirmFSM.waiting)
        await state.update_data(pending=payload)
        await message.answer(
            f"⏳ Подтвердить действие?\n"
            f"🌿 Растение: <code>{plant_id}</code>\n"
            f"📋 {payload['action_text']}\n"
            f"📅 Дата: <code>{payload['new_value']}</code>",
            reply_markup=confirm_keyboard(),
        )
        return

    try:
        sha = await _execute_action(payload, cfg=cfg, db=db)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked action: {}", exc)
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action=f"{action}_blocked",
            payload={"reason": str(exc)},
            file=f"{plant_id}.md",
        )
        await message.answer(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("action {} failed", action)
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    await message.answer(
        f"✅ <code>{plant_id}</code>: {payload['action_text']}\n"
        f"Поле <code>{payload['field']}</code> = <code>{payload['new_value']}</code>\n"
        f"Коммит: <code>{sha[:10]}</code>"
    )


@router.callback_query(ActionConfirmFSM.waiting, F.data.in_({"action:confirm", "action:cancel"}))
async def confirm_callback(
    callback: CallbackQuery,
    state: FSMContext,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
) -> None:
    await callback.answer()

    if callback.data == "action:cancel":
        await state.clear()
        await callback.message.edit_text("❌ Отменено.")
        return

    data = await state.get_data()
    payload = data["pending"]
    await state.clear()

    try:
        if payload.get("action") == "note":
            sha = await _execute_note(payload, cfg=cfg, db=db)
        else:
            sha = await _execute_action(payload, cfg=cfg, db=db)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked action: {}", exc)
        await audit_svc.record(
            db,
            tg_id=payload["tg_id"],
            action=f"{payload['action']}_blocked",
            payload={"reason": str(exc)},
            file=f"{payload['plant_id']}.md",
        )
        await callback.message.edit_text(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("action {} failed", payload.get("action"))
        await callback.message.edit_text(f"Ритуал прерван: <code>{exc}</code>")
        return

    if payload.get("action") == "note":
        await callback.message.edit_text(
            f"📝 <code>{payload['plant_id']}</code>: заметка добавлена.\nКоммит: <code>{sha[:10]}</code>"
        )
    else:
        await callback.message.edit_text(
            f"✅ <code>{payload['plant_id']}</code>: {payload['action_text']}\n"
            f"Поле <code>{payload['field']}</code> = <code>{payload['new_value']}</code>\n"
            f"Коммит: <code>{sha[:10]}</code>"
        )


@router.message(Command("water"))
@requires_role("editor")
async def cmd_water(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    await _apply_action(message, command, action="water", cfg=cfg, db=db, user=user, state=state)


@router.message(Command("fertilize"))
@requires_role("editor")
async def cmd_fertilize(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    await _apply_action(message, command, action="fertilize", cfg=cfg, db=db, user=user, state=state)


@router.message(Command("repot"))
@requires_role("editor")
async def cmd_repot(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    await _apply_action(message, command, action="repot", cfg=cfg, db=db, user=user, state=state)


@router.message(Command("note"))
@requires_role("editor")
async def cmd_note(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    note_text = (command.args or "").strip()
    if not note_text:
        await message.answer("Укажи текст заметки: <code>/note &lt;текст&gt;</code>")
        return

    sess = await sessions_repo.get(db, user.tg_id)
    if not sess or not sess.current_plant_id:
        await message.answer("Сначала выбери растение через /plants.")
        return

    plant_id = sess.current_plant_id
    path = cfg.repository.require_local_path() / f"{plant_id}.md"
    if not path.exists():
        await message.answer(f"Файл карточки <code>{plant_id}.md</code> не найден.")
        return

    today = date.today()
    payload = {
        "plant_id": plant_id,
        "action": "note",
        "note_text": note_text,
        "new_value": today.isoformat(),
        "commit_msg": f"chore(auto): note {plant_id}\n\n{note_text}\nGrimSprout: tg_id={user.tg_id}",
        "tg_id": user.tg_id,
    }

    if cfg.repository.confirm_commits:
        await state.set_state(ActionConfirmFSM.waiting)
        await state.update_data(pending=payload)
        await message.answer(
            f"⏳ Подтвердить заметку?\n🌿 Растение: <code>{plant_id}</code>\n📋 {note_text}",
            reply_markup=confirm_keyboard(),
        )
        return

    try:
        sha = await _execute_note(payload, cfg=cfg, db=db)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked note: {}", exc)
        await message.answer(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("note failed")
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    await message.answer(f"📝 <code>{plant_id}</code>: заметка добавлена.\nКоммит: <code>{sha[:10]}</code>")


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
