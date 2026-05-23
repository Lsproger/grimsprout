"""Bot bootstrap: Dispatcher, middlewares, handlers registration."""

from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from loguru import logger

from grimsprout.bot.handlers import actions, admin, llm_router, plants, start
from grimsprout.bot.handlers import git as git_handlers
from grimsprout.bot.handlers import photo as photo_handlers
from grimsprout.bot.middlewares.auth import AuthMiddleware
from grimsprout.config import load_config
from grimsprout.db.client import get_db, init_indexes
from grimsprout.db.repositories import users as users_repo
from grimsprout.services.repo_bootstrap import ensure_workdir
from grimsprout.utils.logging import setup_logging

BOT_COMMANDS = [
    BotCommand(command="start", description="Приветствие"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="whoami", description="Кто я в склепе"),
    BotCommand(command="plants", description="Список растений"),
    BotCommand(command="water", description="Зафиксировать полив"),
    BotCommand(command="fertilize", description="Зафиксировать удобрение"),
    BotCommand(command="repot", description="Зафиксировать пересадку"),
    BotCommand(command="push", description="Отправить ветку бота в remote"),
    BotCommand(command="pr", description="Открыть PR в базовую ветку"),
]


async def run() -> None:
    cfg = load_config()
    setup_logging(cfg.logging.level, cfg.logging.json_format)

    ensure_workdir(cfg)

    token = os.environ.get(cfg.telegram.token_env)
    if not token:
        raise RuntimeError(f"Telegram bot token not set ({cfg.telegram.token_env})")

    db = get_db()
    await init_indexes(db)
    inserted = await users_repo.ensure_bootstrap_admin(db, cfg.telegram.bootstrap_admin_tg_id)
    if inserted:
        logger.info("bootstrap admin inserted: tg_id={id}", id=cfg.telegram.bootstrap_admin_tg_id)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode(cfg.telegram.parse_mode)),
    )
    dp = Dispatcher()
    dp["db"] = db
    dp["cfg"] = cfg

    auth_mw = AuthMiddleware(db)
    dp.message.middleware(auth_mw)
    dp.callback_query.middleware(auth_mw)

    start.register(dp)
    plants.register(dp)
    actions.register(dp)
    admin.register(dp)
    git_handlers.register(dp)
    photo_handlers.register(dp)
    llm_router.register(dp)  # LAST: catch-all for free text

    me = await bot.get_me()
    logger.info("bot online: @{u} (id={id})", u=me.username, id=me.id)
    logger.info("admin tg_id (config): {a}", a=cfg.telegram.bootstrap_admin_tg_id)

    await bot.set_my_commands(BOT_COMMANDS)
    try:
        await dp.start_polling(bot, db=db, cfg=cfg)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
