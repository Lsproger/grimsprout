"""Photo handling: download → photo_storage → changelog → git commit."""
from __future__ import annotations

from datetime import date

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.config import AppConfig
from grimsprout.core import changelog, photo_storage, plant_repo
from grimsprout.db.models import User
from grimsprout.db.repositories import sessions as sessions_repo
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError

router = Router(name="photo")


async def _resolve_plant_id(
    message: Message,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    tg_id: int,
) -> str | None:
    """Resolve plant from caption argument or current session."""
    caption = (message.caption or "").strip()
    if caption:
        path = plant_repo.find(cfg.repository.require_local_path(), caption)
        if path is not None:
            return path.stem

    sess = await sessions_repo.get(db, tg_id)
    if sess and sess.current_plant_id:
        return sess.current_plant_id

    await message.answer(
        "Не могу определить растение. Выбери через /plants или укажи id в подписи к фото."
    )
    return None


@router.message(F.photo)
@requires_role("editor")
async def on_photo(
    message: Message,
    bot: Bot,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    plant_id = await _resolve_plant_id(message, cfg, db, user.tg_id)
    if plant_id is None:
        return

    repo_path = cfg.repository.require_local_path()
    card_path = repo_path / f"{plant_id}.md"
    if not card_path.exists():
        await message.answer(f"Карточка <code>{plant_id}.md</code> не найдена в склепе.")
        return

    # Download photo in max quality
    photo = message.photo[-1]  # largest size
    file = await bot.get_file(photo.file_id)
    bio = await bot.download_file(file.file_path)
    data = bio.read()

    # Save to repo/images/
    rel_path = photo_storage.save(
        repo_path, cfg.repository.images_dir, plant_id, data
    )

    # Append changelog entry with photo link
    caption_text = (message.caption or "").strip()
    log_text = caption_text if caption_text else "Фото добавлено."
    today = date.today()
    changelog.append_entry(card_path, today, log_text, photo_rel=rel_path)

    # Git: stage image + card, commit
    image_path = repo_path / rel_path
    try:
        git_service.add(repo_path, [image_path, card_path])
        sha = git_service.commit(
            repo_path,
            f"chore(auto): photo {plant_id}\n\n{log_text}\nGrimSprout: tg_id={user.tg_id}",
        )
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked photo save: {}", exc)
        await message.answer(
            "🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\n"
            f"Подробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("photo commit failed")
        await message.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="photo",
        payload={"plant_id": plant_id, "photo_rel": rel_path},
        file=f"{plant_id}.md",
        commit_sha=sha,
    )
    await message.answer(
        f"📸 Фото сохранено: <code>{rel_path}</code>\n"
        f"Карточка <code>{plant_id}</code> обновлена.\n"
        f"Коммит: <code>{sha[:10]}</code>"
    )


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
