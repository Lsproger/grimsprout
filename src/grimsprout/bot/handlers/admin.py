"""Admin commands: /add_user, /set_role, /list_users."""
from __future__ import annotations

from typing import cast

from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.models import Role, User
from grimsprout.db.repositories import users as users_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services.auth_service import VALID_ROLES, requires_role

router = Router(name="admin")


def _parse_add_user_args(raw: str | None) -> tuple[int, str, str] | str:
    if not raw:
        return "Использование: /add_user &lt;tg_id&gt; &lt;role&gt; [имя]"
    parts = raw.split(maxsplit=2)
    if len(parts) < 2:
        return "Использование: /add_user &lt;tg_id&gt; &lt;role&gt; [имя]"
    try:
        tg_id = int(parts[0])
    except ValueError:
        return f"tg_id должен быть числом, а не <code>{parts[0]}</code>."
    role = parts[1]
    if role not in VALID_ROLES:
        return f"Неизвестная роль <code>{role}</code>. Доступны: {', '.join(VALID_ROLES)}."
    display_name = parts[2] if len(parts) == 3 else ""
    return tg_id, role, display_name


@router.message(Command("add_user"))
@requires_role("admin")
async def cmd_add_user(
    message: Message,
    command: CommandObject,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    parsed = _parse_add_user_args(command.args)
    if isinstance(parsed, str):
        await message.answer(parsed)
        return
    tg_id, role, display_name = parsed
    await users_repo.upsert(
        db,
        User(tg_id=tg_id, role=cast(Role, role), display_name=display_name, added_by=user.tg_id),
    )
    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="add_user",
        payload={"target_tg_id": tg_id, "role": role, "display_name": display_name},
    )
    await message.answer(
        f"➕ <code>{tg_id}</code> зачислен в склеп как <code>{role}</code>."
    )


@router.message(Command("set_role"))
@requires_role("admin")
async def cmd_set_role(
    message: Message,
    command: CommandObject,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    raw = (command.args or "").split()
    if len(raw) != 2:
        await message.answer("Использование: /set_role &lt;tg_id&gt; &lt;role&gt;")
        return
    try:
        tg_id = int(raw[0])
    except ValueError:
        await message.answer(f"tg_id должен быть числом, а не <code>{raw[0]}</code>.")
        return
    role = raw[1]
    if role not in VALID_ROLES:
        await message.answer(
            f"Неизвестная роль <code>{role}</code>. Доступны: {', '.join(VALID_ROLES)}."
        )
        return
    target = await users_repo.get_by_tg_id(db, tg_id)
    if target is None:
        await message.answer(f"Пользователь <code>{tg_id}</code> не найден.")
        return
    await users_repo.set_role(db, tg_id, cast(Role, role))
    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="set_role",
        payload={"target_tg_id": tg_id, "role": role},
    )
    await message.answer(f"🔁 <code>{tg_id}</code>: роль → <code>{role}</code>")


@router.message(Command("list_users"))
@requires_role("admin")
async def cmd_list_users(
    message: Message, db: AsyncIOMotorDatabase, **_: object
) -> None:
    items = await users_repo.list_all(db)
    if not items:
        await message.answer("В склепе пусто.")
        return
    lines = [
        f"<code>{u.tg_id}</code> · <b>{u.role}</b> · {u.display_name or '—'}"
        for u in items
    ]
    await message.answer("👥 Обитатели склепа:\n" + "\n".join(lines))


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
