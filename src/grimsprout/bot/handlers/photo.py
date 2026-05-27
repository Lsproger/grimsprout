"""Photo handling: download → photo_storage → changelog → git commit.

Album (media_group) support: all photos sent as one Telegram album are
buffered for ALBUM_DELAY seconds, then written as a single changelog entry
and committed together.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
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

ALBUM_DELAY = 0.5  # seconds to wait for remaining album photos

# media_group_id → list of (message, downloaded_bytes)
_album_buffer: dict[str, list[tuple[Message, bytes]]] = defaultdict(list)
# media_group_id → (cfg, db, user) captured from the first photo in the group
_album_context: dict[str, tuple[AppConfig, AsyncIOMotorDatabase, User]] = {}
# media_group_id → pending asyncio.Task
_album_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]


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

    await message.answer("Не могу определить растение. Выбери через /plants или укажи id в подписи к фото.")
    return None


async def _flush_album(group_id: str) -> None:
    """Process all buffered photos from a media group as one commit."""
    entries = _album_buffer.pop(group_id, [])
    ctx = _album_context.pop(group_id, None)
    _album_tasks.pop(group_id, None)

    if not entries or ctx is None:
        return

    cfg, db, user = ctx
    first_msg = entries[0][0]

    plant_id = await _resolve_plant_id(first_msg, cfg, db, user.tg_id)
    if plant_id is None:
        return

    repo_path = cfg.repository.require_local_path()
    card_path = repo_path / f"{plant_id}.md"
    if not card_path.exists():
        await first_msg.answer(f"Карточка <code>{plant_id}.md</code> не найдена в склепе.")
        return

    # Use caption from whichever message in the group carries it
    caption_text = next((msg.caption.strip() for msg, _ in entries if msg.caption), "")
    log_text = caption_text if caption_text else "Фото добавлено."

    # Save all photos
    today = date.today()
    rel_paths: list[str] = []
    image_paths = []
    for _, data in entries:
        rel_path = photo_storage.save(repo_path, cfg.repository.images_dir, plant_id, data)
        rel_paths.append(rel_path)
        image_paths.append(repo_path / rel_path)

    # One changelog entry with all photo links
    changelog.append_entry(card_path, today, log_text, photo_rels=rel_paths)

    # Git: stage all images + card, one commit
    n = len(rel_paths)
    try:
        git_service.add(repo_path, [*image_paths, card_path])
        sha = git_service.commit(
            repo_path,
            f"chore(auto): photo {plant_id} ({n} img)\n\n{log_text}\nGrimSprout: tg_id={user.tg_id}",
        )
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked photo save: {}", exc)
        await first_msg.answer(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("photo commit failed")
        await first_msg.answer(f"Ритуал прерван: <code>{exc}</code>")
        return

    for rel_path in rel_paths:
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="photo",
            payload={"plant_id": plant_id, "photo_rel": rel_path},
            file=f"{plant_id}.md",
            commit_sha=sha,
        )

    photos_list = "\n".join(f"<code>{p}</code>" for p in rel_paths)
    await first_msg.answer(
        f"📸 {n} фото сохранено:\n{photos_list}\n"
        f"Карточка <code>{plant_id}</code> обновлена.\n"
        f"Коммит: <code>{sha[:10]}</code>"
    )


async def _process_single_photo(
    message: Message,
    data: bytes,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> None:
    """Handle a lone (non-album) photo."""
    plant_id = await _resolve_plant_id(message, cfg, db, user.tg_id)
    if plant_id is None:
        return

    repo_path = cfg.repository.require_local_path()
    card_path = repo_path / f"{plant_id}.md"
    if not card_path.exists():
        await message.answer(f"Карточка <code>{plant_id}.md</code> не найдена в склепе.")
        return

    caption_text = (message.caption or "").strip()
    log_text = caption_text if caption_text else "Фото добавлено."
    today = date.today()

    rel_path = photo_storage.save(repo_path, cfg.repository.images_dir, plant_id, data)
    changelog.append_entry(card_path, today, log_text, photo_rels=[rel_path])

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
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>"
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
    # Download photo in max quality
    photo = message.photo[-1]  # largest size
    file = await bot.get_file(photo.file_id)
    bio = await bot.download_file(file.file_path)
    data = bio.read()

    group_id = message.media_group_id
    if group_id is None:
        await _process_single_photo(message, data, cfg, db, user)
        return

    # Album: buffer photo and (re)schedule delayed flush
    _album_buffer[group_id].append((message, data))
    if group_id not in _album_context:
        _album_context[group_id] = (cfg, db, user)

    # Cancel previous task and extend the collection window
    if group_id in _album_tasks:
        _album_tasks[group_id].cancel()

    async def _delayed(gid: str) -> None:
        await asyncio.sleep(ALBUM_DELAY)
        try:
            await _flush_album(gid)
        except Exception:
            logger.exception("album flush failed for group_id={}", gid)
            _album_buffer.pop(gid, None)
            _album_context.pop(gid, None)
            _album_tasks.pop(gid, None)

    _album_tasks[group_id] = asyncio.create_task(_delayed(group_id))


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
