"""Direct commands: /water, /fertilize, /repot.

Resolution order for the target plant:
1. Command argument (e.g. `/water calathea_01` or `/water Калатея`)
2. `sessions.current_plant_id` of the user

On success: updates YAML date field, appends a changelog entry, stages and
commits the .md file in the trava repo. Photo handling is out of scope here.
"""
from __future__ import annotations

from datetime import date

from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

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
            await message.answer(
                f"Не нашёл растения по запросу: <code>{arg}</code>. Попробуй /plants."
            )
            return None
        return path.stem

    sess = await sessions_repo.get(db, tg_id)
    if sess and sess.current_plant_id:
        return sess.current_plant_id

    await message.answer(
        "Сначала выбери растение через /plants или укажи id аргументом."
    )
    return None


async def _apply_action(
    message: Message,
    command: CommandObject,
    *,
    action: str,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> None:
    plant_id = await _resolve_plant_id(message, command, cfg, db, user.tg_id)
    if plant_id is None:
        return

    field, text = ACTIONS[action]
    path = cfg.repository.require_local_path() / f"{plant_id}.md"
    if not path.exists():
        await message.answer(f"Файл карточки <code>{plant_id}.md</code> не найден.")
        return

    today = date.today()
    try:
        md_parser.update_yaml(path, {field: today.isoformat()})
        changelog.append_entry(path, today, text)
        git_service.add(cfg.repository.require_local_path(), [path])
        sha = git_service.commit(
            cfg.repository.require_local_path(),
            f"chore(auto): {action} {plant_id}\n\n{text}\nGrimSprout: tg_id={user.tg_id}",
        )
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
            "🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\n"
            f"Подробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("action {} failed", action)
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action=action,
        payload={"plant_id": plant_id},
        file=f"{plant_id}.md",
        commit_sha=sha,
    )
    await message.answer(
        f"✅ <code>{plant_id}</code>: {text}\n"
        f"Поле <code>{field}</code> = <code>{today.isoformat()}</code>\n"
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
    **_: object,
) -> None:
    await _apply_action(message, command, action="water", cfg=cfg, db=db, user=user)


@router.message(Command("fertilize"))
@requires_role("editor")
async def cmd_fertilize(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    await _apply_action(message, command, action="fertilize", cfg=cfg, db=db, user=user)


@router.message(Command("repot"))
@requires_role("editor")
async def cmd_repot(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    await _apply_action(message, command, action="repot", cfg=cfg, db=db, user=user)


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
