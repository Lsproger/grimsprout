"""/new — FSM-create a new plant card in the trava repo."""

from __future__ import annotations

from datetime import date

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.bot.states import NewCardFSM
from grimsprout.config import AppConfig
from grimsprout.core import md_parser
from grimsprout.core.ids import next_slug, slugify
from grimsprout.db.models import User
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError

router = Router(name="new_card")

_AGE_GROUP_OPTIONS = ["seedling", "juvenile", "adult"]


def _age_group_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for v in _AGE_GROUP_OPTIONS:
        kb.button(text=v, callback_data=f"new:age:{v}")
    kb.button(text="⏭ Пропустить", callback_data="new:age:skip")
    kb.adjust(2)
    return kb.as_markup()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Создать", callback_data="new:confirm")
    kb.button(text="❌ Отменить", callback_data="new:cancel")
    kb.adjust(2)
    return kb.as_markup()


def _preview(data: dict) -> str:
    lines = ["📋 <b>Новое растение — предпросмотр:</b>"]
    lines.append(f"  <b>Название:</b> {data.get('common_name', '—')}")
    if data.get("botanical_name"):
        lines.append(f"  <b>Научное:</b> {data['botanical_name']}")
    if data.get("variety"):
        lines.append(f"  <b>Сорт:</b> {data['variety']}")
    if data.get("purchase_date"):
        lines.append(f"  <b>Куплено:</b> {data['purchase_date']}")
    if data.get("purchase_location"):
        lines.append(f"  <b>Откуда:</b> {data['purchase_location']}")
    if data.get("age_group"):
        lines.append(f"  <b>Возраст:</b> {data['age_group']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1: /new
# ---------------------------------------------------------------------------


@router.message(Command("new"))
@requires_role("editor")
async def cmd_new(
    message: Message,
    state: FSMContext,
    **_: object,
) -> None:
    await state.clear()
    await state.set_state(NewCardFSM.common_name)
    await message.answer(
        "🌱 Создание новой карточки.\n\nВведи <b>название растения</b> (например, «Монстера»):"
    )


# ---------------------------------------------------------------------------
# Step 2: common_name
# ---------------------------------------------------------------------------


@router.message(NewCardFSM.common_name)
async def on_common_name(message: Message, state: FSMContext, **_: object) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Название не может быть пустым. Введи ещё раз:")
        return
    await state.update_data(common_name=text)
    await state.set_state(NewCardFSM.botanical_name)
    await message.answer("Введи <b>научное (ботаническое) название</b>:\nили /skip чтобы пропустить.")


# ---------------------------------------------------------------------------
# Step 3: botanical_name
# ---------------------------------------------------------------------------


@router.message(NewCardFSM.botanical_name)
async def on_botanical_name(message: Message, state: FSMContext, **_: object) -> None:
    text = (message.text or "").strip()
    await state.update_data(botanical_name="" if text.lower() == "/skip" else text)
    await state.set_state(NewCardFSM.variety)
    await message.answer("Введи <b>сорт / разновидность</b> (если есть):\nили /skip чтобы пропустить.")


# ---------------------------------------------------------------------------
# Step 4: variety
# ---------------------------------------------------------------------------


@router.message(NewCardFSM.variety)
async def on_variety(message: Message, state: FSMContext, **_: object) -> None:
    text = (message.text or "").strip()
    await state.update_data(variety="" if text.lower() == "/skip" else text)
    await state.set_state(NewCardFSM.purchase_date)
    await message.answer("Введи <b>дату приобретения</b> в формате ГГГГ-ММ-ДД:\nили /skip чтобы пропустить.")


# ---------------------------------------------------------------------------
# Step 5: purchase_date
# ---------------------------------------------------------------------------


@router.message(NewCardFSM.purchase_date)
async def on_purchase_date(message: Message, state: FSMContext, **_: object) -> None:
    text = (message.text or "").strip()
    if text.lower() == "/skip":
        await state.update_data(purchase_date="")
    else:
        try:
            date.fromisoformat(text)
        except ValueError:
            await message.answer("Неверный формат. Ожидается ГГГГ-ММ-ДД (например, 2026-01-15).\nИли /skip.")
            return
        await state.update_data(purchase_date=text)
    await state.set_state(NewCardFSM.purchase_location)
    await message.answer("Введи <b>место приобретения</b> (например, IKEA):\nили /skip чтобы пропустить.")


# ---------------------------------------------------------------------------
# Step 6: purchase_location
# ---------------------------------------------------------------------------


@router.message(NewCardFSM.purchase_location)
async def on_purchase_location(message: Message, state: FSMContext, **_: object) -> None:
    text = (message.text or "").strip()
    await state.update_data(purchase_location="" if text.lower() == "/skip" else text)
    await state.set_state(NewCardFSM.age_group)
    await message.answer(
        "Выбери <b>возрастную группу</b>:",
        reply_markup=_age_group_keyboard(),
    )


# ---------------------------------------------------------------------------
# Step 7: age_group (inline callback)
# ---------------------------------------------------------------------------


@router.callback_query(NewCardFSM.age_group, F.data.startswith("new:age:"))
async def on_age_group(cq, state: FSMContext, **_: object) -> None:
    await cq.answer()
    value = (cq.data or "").split(":", 2)[2]
    await state.update_data(age_group="" if value == "skip" else value)
    await state.set_state(NewCardFSM.confirm)
    data = await state.get_data()
    if isinstance(cq.message, Message):
        await cq.message.edit_text(
            _preview(data) + "\n\nПодтвердить создание?",
            reply_markup=_confirm_keyboard(),
        )


# ---------------------------------------------------------------------------
# Step 8: confirm / cancel
# ---------------------------------------------------------------------------


@router.callback_query(NewCardFSM.confirm, F.data.in_({"new:confirm", "new:cancel"}))
async def on_confirm(
    cq,
    state: FSMContext,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    await cq.answer()
    if cq.data == "new:cancel":
        await state.clear()
        if isinstance(cq.message, Message):
            await cq.message.edit_text("Создание отменено.")
        return

    data = await state.get_data()
    await state.clear()

    common_name: str = data["common_name"]
    repo_path = cfg.repository.require_local_path()
    base_slug = slugify(common_name)
    plant_id = next_slug(repo_path, base_slug)
    path = repo_path / f"{plant_id}.md"

    yaml_data: dict = {
        "id": plant_id,
        "status": "alive",
        "common_name": common_name,
    }
    for key in ("botanical_name", "variety", "purchase_date", "purchase_location", "age_group"):
        if data.get(key):
            yaml_data[key] = data[key]

    body = (
        f"# {common_name} (ID: {plant_id})\n\n"
        "## Журнал изменений (Changelog)\n\n"
        f"- **{date.today().isoformat()}**: Карточка создана.\n"
    )

    try:
        md_parser.write(path, yaml_data, body)
        git_service.add(repo_path, [path])
        sha = git_service.commit(
            repo_path,
            f"feat(plant): add {plant_id}\n\nGrimSprout: tg_id={user.tg_id}",
        )
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked new card: {}", exc)
        if isinstance(cq.message, Message):
            await cq.message.edit_text(
                f"🪦 Склеп в беспорядке — посторонние правки блокируют запись.\n<code>{exc}</code>"
            )
        return
    except GrimSproutError as exc:
        logger.exception("new_card failed for plant={}", plant_id)
        if isinstance(cq.message, Message):
            await cq.message.edit_text(f"Ритуал прерван: <code>{exc}</code>")
        return

    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="create_plant",
        payload={"plant_id": plant_id},
        file=f"{plant_id}.md",
        commit_sha=sha,
    )

    if isinstance(cq.message, Message):
        await cq.message.edit_text(
            f"🌱 Растение <code>{plant_id}</code> добавлено в склеп.\nКоммит: <code>{sha[:10]}</code>"
        )


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
