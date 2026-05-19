"""/plants — list plants and select current via inline keyboard."""
from __future__ import annotations

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from motor.motor_asyncio import AsyncIOMotorDatabase
from grimsprout.bot.keyboards import plants_keyboard
from grimsprout.config import AppConfig
from grimsprout.core import plant_repo
from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services.auth_service import requires_role

router = Router(name="plants")


@router.message(Command("plants"))
@requires_role("viewer")
async def cmd_plants(
    message: Message, cfg: AppConfig, user: User, **_: object
) -> None:
    items = plant_repo.list_plants(cfg.repository.require_local_path())
    if not items:
        await message.answer("В склепе пока ни одного растения. Используй /new.")
        return
    await message.answer(
        f"🌿 Растений в склепе: <b>{len(items)}</b>. Выбери текущее:",
        reply_markup=plants_keyboard(items),
    )


@router.callback_query(F.data.startswith("plant:set:"))
@requires_role("viewer")
async def on_select_plant(
    cq: CallbackQuery,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    data = cq.data or ""
    plant_id = data.split(":", 2)[2] if data.count(":") >= 2 else ""
    if not plant_id:
        await cq.answer("Не распознал выбор.")
        return
    await sessions_repo.set_current_plant(db, user.tg_id, plant_id)
    await audit_svc.record(
        db, tg_id=user.tg_id, action="select_plant", payload={"plant_id": plant_id}
    )
    await cq.answer(f"Выбрано: {plant_id}")
    if isinstance(cq.message, Message):
        try:
            await cq.message.edit_text(
                f"Текущее растение: <code>{plant_id}</code>"
            )
        except Exception:
            pass


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
