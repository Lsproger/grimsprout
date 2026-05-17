"""AuthMiddleware: resolves Telegram user → role from MongoDB.

Behavior:
- Known user (found in `users`) → injects `user` and `role` into handler kwargs.
- Unknown user → writes audit `access_denied`, replies with a stylized stub,
  notifies the first admin in DM (deduped per-process). Stops handler chain.
"""
from __future__ import annotations

import html
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.repositories import users as users_repo
from grimsprout.services import audit as audit_svc


DENY_MESSAGE = "🪦 Склеп заперт. Доступ запрещён."


class AuthMiddleware(BaseMiddleware):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._notified: set[int] = set()
        self._admin_chat_id: int | None = None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user is None:
            # Service events without a user — pass through with no role.
            data["user"] = None
            data["role"] = None
            return await handler(event, data)

        user = await users_repo.get_by_tg_id(self.db, tg_user.id)
        if user is not None:
            data["user"] = user
            data["role"] = user.role
            return await handler(event, data)

        # Unknown user → deny + notify
        text_sample = ""
        if isinstance(event, Message):
            text_sample = (event.text or event.caption or "")[:200]
        elif isinstance(event, CallbackQuery):
            text_sample = event.data or ""

        await audit_svc.record(
            self.db,
            tg_id=tg_user.id,
            action="access_denied",
            payload={
                "username": tg_user.username or "",
                "full_name": tg_user.full_name or "",
                "text": text_sample,
            },
        )

        if isinstance(event, Message):
            try:
                await event.answer(DENY_MESSAGE)
            except Exception as exc:  # pragma: no cover
                logger.warning("deny reply failed: {}", exc)
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(DENY_MESSAGE, show_alert=True)
            except Exception as exc:  # pragma: no cover
                logger.warning("deny callback answer failed: {}", exc)

        await self._notify_admin(event, tg_user)
        return None  # stop chain

    async def _notify_admin(self, event: TelegramObject, tg_user: Any) -> None:
        if tg_user.id in self._notified:
            return
        self._notified.add(tg_user.id)

        if self._admin_chat_id is None:
            admin = await users_repo.find_first_admin(self.db)
            if admin is None:
                logger.warning("no admin in users collection; cannot notify about {}", tg_user.id)
                return
            self._admin_chat_id = admin.tg_id

        bot = getattr(event, "bot", None)
        if bot is None:
            return

        uname = f"@{tg_user.username}" if tg_user.username else "—"
        full = html.escape(tg_user.full_name or "")
        msg = (
            "🪦 Новый незваный гость стучится в склеп:\n"
            f"<b>{full}</b> {html.escape(uname)}\n"
            f"tg_id: <code>{tg_user.id}</code>"
        )
        try:
            await bot.send_message(self._admin_chat_id, msg)
        except Exception as exc:  # pragma: no cover
            logger.warning("admin notify failed: {}", exc)
