"""/edit — Edit individual fields on a plant card.

Two modes:
  Quick:       /edit <field> <value>   — single-step update
  Interactive: /edit                   — FSM: choose field → enter value
"""

from __future__ import annotations

from datetime import date
from typing import Any

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.bot.keyboards import enum_value_keyboard, field_selection_keyboard
from grimsprout.bot.states import EditFSM
from grimsprout.config import AppConfig
from grimsprout.core import changelog, md_parser, plant_repo
from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError

router = Router(name="edit")

# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------

_ENUM_OPTIONS: dict[str, list[str]] = {
    "status": ["alive", "dead", "sold", "gifted"],
    "pot_type": ["plastic", "terracotta", "ceramic", "self-watering"],
    "age_group": ["seedling", "juvenile", "adult"],
}

_FIELD_LABELS: dict[str, str] = {
    "status": "Статус",
    "health_score": "Здоровье (1.0–10.0)",
    "common_name": "Название",
    "botanical_name": "Научное название",
    "age_group": "Возраст",
    "pot_size_cm": "Горшок (1–100 см)",
    "pot_type": "Тип горшка",
    "light_req": "Освещение",
    "soil_type": "Грунт",
    "humidity_req": "Влажность (0–100%)",
    "purchase_location": "Откуда",
    "tags": "Теги (+тег / -тег)",
}

EDITABLE_FIELDS = set(_FIELD_LABELS)


def _parse_value(field: str, raw: str) -> tuple[Any, str]:
    """Parse and validate raw string for the given field.

    Returns (parsed_value, error_message). error_message is empty on success.
    """
    raw = raw.strip()

    if field in _ENUM_OPTIONS:
        if raw not in _ENUM_OPTIONS[field]:
            opts = ", ".join(_ENUM_OPTIONS[field])
            return None, f"Допустимые значения: {opts}"
        return raw, ""

    if field == "health_score":
        try:
            v = float(raw)
        except ValueError:
            return None, "Ожидается число (например, 7.5)"
        if not (1.0 <= v <= 10.0):
            return None, "Значение должно быть от 1.0 до 10.0"
        return v, ""

    if field == "pot_size_cm":
        try:
            v = int(raw)
        except ValueError:
            return None, "Ожидается целое число (например, 17)"
        if not (1 <= v <= 100):
            return None, "Значение должно быть от 1 до 100"
        return v, ""

    if field == "humidity_req":
        try:
            v = int(raw)
        except ValueError:
            return None, "Ожидается целое число (например, 70)"
        if not (0 <= v <= 100):
            return None, "Значение должно быть от 0 до 100"
        return v, ""

    if field == "tags":
        # handled separately via _apply_tag_patch
        return raw, ""

    # String fields — no special validation
    if not raw:
        return None, "Значение не может быть пустым"
    return raw, ""


def _apply_tag_patch(current_tags: list[str], raw: str) -> tuple[list[str], str]:
    """Process +tag / -tag syntax. Returns (new_tags, error_message)."""
    parts = raw.strip().split()
    tags = list(current_tags)
    for part in parts:
        if part.startswith("+"):
            tag = part[1:]
            if tag and tag not in tags:
                tags.append(tag)
        elif part.startswith("-"):
            tag = part[1:]
            tags = [t for t in tags if t != tag]
        else:
            return [], "Теги должны начинаться с + (добавить) или - (убрать). Пример: +пальма -тест"
    return tags, ""


# ---------------------------------------------------------------------------
# Core apply logic
# ---------------------------------------------------------------------------


async def _apply_edit(
    *,
    plant_id: str,
    field: str,
    new_value: Any,
    tg_id: int,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
) -> str:
    """Write the field change to disk, append changelog, commit. Returns SHA."""
    repo_path = cfg.repository.require_local_path()
    path = repo_path / f"{plant_id}.md"

    md_parser.update_yaml(path, {field: new_value})
    changelog.append_entry(
        path,
        date.today(),
        f"Изменено поле {field} → {new_value}",
    )
    git_service.add(repo_path, [path])
    sha = git_service.commit(
        repo_path,
        f"chore(edit): {plant_id} {field}\n\nGrimSprout: tg_id={tg_id}",
    )
    await audit_svc.record(
        db,
        tg_id=tg_id,
        action="edit_field",
        payload={"plant_id": plant_id, "field": field, "new_value": str(new_value)},
        file=f"{plant_id}.md",
        commit_sha=sha,
    )
    return sha


async def _do_apply(
    message: Message,
    *,
    plant_id: str,
    field: str,
    new_value: Any,
    user: User,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
) -> None:
    try:
        sha = await _apply_edit(
            plant_id=plant_id,
            field=field,
            new_value=new_value,
            tg_id=user.tg_id,
            cfg=cfg,
            db=db,
        )
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked edit: {}", exc)
        await message.answer(
            f"🪦 Склеп в беспорядке — посторонние правки блокируют запись.\n<code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("edit_field failed for plant={}", plant_id)
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    await message.answer(
        f"✅ <code>{plant_id}</code>: поле <code>{field}</code> обновлено → <code>{new_value}</code>\n"
        f"Коммит: <code>{sha[:10]}</code>"
    )


# ---------------------------------------------------------------------------
# Plant resolution helper
# ---------------------------------------------------------------------------


async def _resolve_plant_id(
    message: Message,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    tg_id: int,
    arg: str = "",
) -> str | None:
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


# ---------------------------------------------------------------------------
# /edit command
# ---------------------------------------------------------------------------


@router.message(Command("edit"))
@requires_role("editor")
async def cmd_edit(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    args = (command.args or "").strip().split(None, 1)

    # --- Interactive mode: /edit (no args) ---
    if not args or not args[0]:
        plant_id = await _resolve_plant_id(message, cfg, db, user.tg_id)
        if plant_id is None:
            return
        await state.set_state(EditFSM.choosing_field)
        await state.update_data(plant_id=plant_id)
        await message.answer(
            f"✏️ Редактирование <code>{plant_id}</code>. Выбери поле:",
            reply_markup=field_selection_keyboard(),
        )
        return

    # --- Quick mode with only field: /edit <field> (no value) ---
    if len(args) == 1:
        field = args[0].lower()
        if field not in EDITABLE_FIELDS:
            await message.answer(
                f"Неизвестное поле: <code>{field}</code>\nДоступные: {', '.join(sorted(EDITABLE_FIELDS))}"
            )
            return
        plant_id = await _resolve_plant_id(message, cfg, db, user.tg_id)
        if plant_id is None:
            return
        await state.set_state(EditFSM.entering_value)
        await state.update_data(plant_id=plant_id, field=field)
        kb = enum_value_keyboard(field)
        prompt = f"Введи новое значение для <b>{_FIELD_LABELS[field]}</b>:"
        await message.answer(prompt, reply_markup=kb)
        return

    # --- Quick mode: /edit <field> <value> ---
    field, raw_value = args[0].lower(), args[1]
    if field not in EDITABLE_FIELDS:
        await message.answer(
            f"Неизвестное поле: <code>{field}</code>\nДоступные: {', '.join(sorted(EDITABLE_FIELDS))}"
        )
        return

    # Resolve plant (optionally first token of raw_value could be plant_id,
    # but simpler: use session/current)
    plant_id = await _resolve_plant_id(message, cfg, db, user.tg_id)
    if plant_id is None:
        return

    if field == "tags":
        card = plant_repo.read_card(cfg.repository.require_local_path(), plant_id)
        current_tags: list[str] = (card[0].get("tags") or []) if card else []
        new_value, err = _apply_tag_patch(current_tags, raw_value)
        if err:
            await message.answer(f"⚠️ {err}")
            return
    else:
        new_value, err = _parse_value(field, raw_value)
        if err:
            await message.answer(f"⚠️ {err}")
            return

    path = cfg.repository.require_local_path() / f"{plant_id}.md"
    if not path.exists():
        await message.answer(f"Файл карточки <code>{plant_id}.md</code> не найден.")
        return

    await _do_apply(message, plant_id=plant_id, field=field, new_value=new_value, user=user, cfg=cfg, db=db)


# ---------------------------------------------------------------------------
# FSM: field selection callback
# ---------------------------------------------------------------------------


@router.callback_query(EditFSM.choosing_field, F.data.startswith("edit:field:"))
@requires_role("editor")
async def on_choose_field(
    cq: CallbackQuery,
    state: FSMContext,
    **_: object,
) -> None:
    await cq.answer()
    field = (cq.data or "").split(":", 2)[2]
    if field not in EDITABLE_FIELDS:
        await cq.answer("Неизвестное поле.", show_alert=True)
        return

    await state.update_data(field=field)
    await state.set_state(EditFSM.entering_value)

    kb = enum_value_keyboard(field)
    prompt = f"Введи новое значение для <b>{_FIELD_LABELS[field]}</b>:"
    if isinstance(cq.message, Message):
        await cq.message.edit_text(prompt, reply_markup=kb)


# ---------------------------------------------------------------------------
# FSM: cancel callback (both states)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "edit:cancel")
async def on_edit_cancel(cq: CallbackQuery, state: FSMContext, **_: object) -> None:
    await cq.answer()
    await state.clear()
    if isinstance(cq.message, Message):
        await cq.message.edit_text("Редактирование отменено.")


# ---------------------------------------------------------------------------
# FSM: value entry — enum via callback
# ---------------------------------------------------------------------------


@router.callback_query(EditFSM.entering_value, F.data.startswith("edit:value:"))
@requires_role("editor")
async def on_choose_enum_value(
    cq: CallbackQuery,
    state: FSMContext,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    await cq.answer()
    data = await state.get_data()
    plant_id: str = data["plant_id"]
    field: str = data["field"]
    raw_value = (cq.data or "").split(":", 2)[2]

    new_value, err = _parse_value(field, raw_value)
    if err:
        if isinstance(cq.message, Message):
            await cq.message.edit_text(f"⚠️ {err}")
        await state.clear()
        return

    await state.clear()
    if isinstance(cq.message, Message):
        await _do_apply(
            cq.message,
            plant_id=plant_id,
            field=field,
            new_value=new_value,
            user=user,
            cfg=cfg,
            db=db,
        )


# ---------------------------------------------------------------------------
# FSM: value entry — free text
# ---------------------------------------------------------------------------


@router.message(EditFSM.entering_value)
@requires_role("editor")
async def on_enter_value(
    message: Message,
    state: FSMContext,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    data = await state.get_data()
    plant_id: str = data["plant_id"]
    field: str = data["field"]
    raw_value = (message.text or "").strip()

    if field == "tags":
        card = plant_repo.read_card(cfg.repository.require_local_path(), plant_id)
        current_tags: list[str] = (card[0].get("tags") or []) if card else []
        new_value, err = _apply_tag_patch(current_tags, raw_value)
    else:
        new_value, err = _parse_value(field, raw_value)

    if err:
        await message.answer(f"⚠️ {err}\nПопробуй ещё раз или /cancel.")
        return

    await state.clear()
    await _do_apply(message, plant_id=plant_id, field=field, new_value=new_value, user=user, cfg=cfg, db=db)


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
