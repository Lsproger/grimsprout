"""/start, /help, /whoami — basic introductory commands."""

from __future__ import annotations

import html

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services.auth_service import has_role

router = Router(name="start")


HELP_LINES_COMMON = [
    "/start — приветствие",
    "/help — справка",
    "/whoami — кто я в склепе",
    "/plants — список растений и выбор текущего",
]
HELP_LINES_EDITOR = [
    "/water [id] — зафиксировать полив",
    "/fertilize [id] — зафиксировать удобрение",
    "/repot [id] — зафиксировать пересадку",
]
HELP_LINES_ADMIN = [
    "/add_user &lt;tg_id&gt; &lt;role&gt; [имя] — добавить пользователя",
    "/set_role &lt;tg_id&gt; &lt;role&gt; — сменить роль",
    "/list_users — список обитателей склепа",
]


@router.message(Command("start"))
async def cmd_start(message: Message, user: User, **_: object) -> None:
    name = html.escape(message.from_user.full_name if message.from_user else "")
    await message.answer(
        f"🪦 Добро пожаловать в склеп, <b>{name}</b>.\nТвоя роль: <code>{user.role}</code>.\nКоманды — /help."
    )


@router.message(Command("help"))
async def cmd_help(message: Message, user: User, **_: object) -> None:
    lines = list(HELP_LINES_COMMON)
    if has_role(user.role, "editor"):
        lines += HELP_LINES_EDITOR
    if has_role(user.role, "admin"):
        lines += HELP_LINES_ADMIN
    await message.answer("Доступные ритуалы:\n" + "\n".join(lines))


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, user: User, db: AsyncIOMotorDatabase, **_: object) -> None:
    sess = await sessions_repo.get(db, user.tg_id)
    current = sess.current_plant_id if sess else None
    await message.answer(
        f"tg_id: <code>{user.tg_id}</code>\n"
        f"role: <code>{user.role}</code>\n"
        f"текущее растение: <code>{current or '—'}</code>"
    )


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
