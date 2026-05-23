"""/info — View plant card summary (YAML fields + last changelog entries)."""

from __future__ import annotations

import re

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.config import AppConfig
from grimsprout.core import plant_repo
from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services.auth_service import requires_role

router = Router(name="info")

_CHANGELOG_RE = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\*: (.+)$", re.MULTILINE)

_FIELD_LABELS: dict[str, str] = {
    "botanical_name": "Научное название",
    "status": "Статус",
    "health_score": "Здоровье",
    "age_group": "Возраст",
    "purchase_date": "Куплено",
    "purchase_location": "Откуда",
    "pot_size_cm": "Горшок (см)",
    "pot_type": "Тип горшка",
    "light_req": "Освещение",
    "moisture_req": "Полив",
    "humidity_req": "Влажность (%)",
    "soil_type": "Грунт",
    "last_watered_date": "Последний полив",
    "last_fertilized_date": "Последнее удобрение",
    "last_repot_date": "Последняя пересадка",
    "tags": "Теги",
}

_STATUS_EMOJI: dict[str, str] = {
    "alive": "🌱",
    "dead": "💀",
    "sold": "💸",
    "gifted": "🎁",
}

_DISPLAY_ORDER = list(_FIELD_LABELS.keys())


def _format_card(yaml_data: dict, body: str) -> str:
    plant_id = yaml_data.get("id", "?")
    name = yaml_data.get("common_name") or plant_id
    status = str(yaml_data.get("status", ""))
    emoji = _STATUS_EMOJI.get(status, "🌿")

    lines: list[str] = [f"{emoji} <b>{name}</b>  <code>{plant_id}</code>"]

    for key in _DISPLAY_ORDER:
        value = yaml_data.get(key)
        if value is None or value == "" or value == []:
            continue
        label = _FIELD_LABELS[key]
        if isinstance(value, list):
            formatted = ", ".join(str(v) for v in value)
        else:
            formatted = str(value)
        lines.append(f"  <b>{label}:</b> {formatted}")

    entries = _CHANGELOG_RE.findall(body)
    if entries:
        lines.append("")
        lines.append("<b>Последние записи:</b>")
        for dt, text in entries[:5]:
            lines.append(f"  <code>{dt}</code> {text}")

    return "\n".join(lines)


async def _resolve_plant_id(
    message: Message,
    command: CommandObject | None,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    tg_id: int,
) -> str | None:
    arg = (command.args or "").strip() if command else ""
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


@router.message(Command("info"))
@requires_role("viewer")
async def cmd_info(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    plant_id = await _resolve_plant_id(message, command, cfg, db, user.tg_id)
    if plant_id is None:
        return

    result = plant_repo.read_card(cfg.repository.require_local_path(), plant_id)
    if result is None:
        await message.answer(f"Карточка <code>{plant_id}</code> не найдена в репозитории.")
        return

    yaml_data, body = result
    await message.answer(_format_card(yaml_data, body))


@router.callback_query(F.data.startswith("plant:info:"))
@requires_role("viewer")
async def on_info_callback(
    cq: CallbackQuery,
    cfg: AppConfig,
    user: User,
    **_: object,
) -> None:
    data = cq.data or ""
    plant_id = data.split(":", 2)[2] if data.count(":") >= 2 else ""
    if not plant_id:
        await cq.answer("Не распознал выбор.")
        return

    result = plant_repo.read_card(cfg.repository.require_local_path(), plant_id)
    if result is None:
        await cq.answer("Карточка не найдена.", show_alert=True)
        return

    yaml_data, body = result
    if isinstance(cq.message, Message):
        await cq.message.answer(_format_card(yaml_data, body))
    await cq.answer()


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
