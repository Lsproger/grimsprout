"""Revert bot commits by short SHA via /revert."""

from __future__ import annotations

import html

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.bot.states import RevertFSM
from grimsprout.config import AppConfig
from grimsprout.db.models import User
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.services.auth_service import requires_role
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError

router = Router(name="revert")

_SHORT_SHA_MIN = 7
_DEFAULT_RECENT_LIMIT = 20


def _to_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def _revert_confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="revert:confirm")
    kb.button(text="❌ Отменить", callback_data="revert:cancel")
    kb.adjust(2)
    return kb.as_markup()


async def _safe_edit_callback_message(callback: CallbackQuery, text: str) -> None:
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(text)
        return
    await callback.answer(text, show_alert=True)


def _parse_revert_args(raw: str) -> tuple[str | None, bool]:
    parts = [p for p in raw.split() if p]
    if not parts:
        return None, False

    short_sha = ""
    hard_mode = False
    for part in parts:
        if part in {"--hard", "-H"}:
            hard_mode = True
            continue
        if short_sha:
            return None, hard_mode
        short_sha = part

    if not short_sha:
        return None, hard_mode
    return short_sha, hard_mode


def _build_preview(*, target_sha: str, summary: str, hard_mode: bool) -> str:
    mode = "hard" if hard_mode else "default"
    return (
        "⏳ Подтвердить откат коммита?\n"
        f"🎯 Цель: <code>{target_sha[:10]}</code>\n"
        f"📝 {html.escape(summary)}\n"
        f"🛡 Режим: <code>{mode}</code>"
    )


async def _execute_revert(
    payload: dict,
    *,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
) -> str:
    repo_path = cfg.repository.require_local_path()
    new_sha = git_service.revert_commit(repo_path, payload["target_sha"])
    await audit_svc.record(
        db,
        tg_id=payload["tg_id"],
        action="revert",
        payload={
            "original_sha": payload["target_sha"],
            "original_short_sha": payload["short_sha"],
            "revert_sha": new_sha,
            "mode": payload["mode"],
            "summary": payload["summary"],
        },
        commit_sha=new_sha,
    )
    return new_sha


@router.message(Command("revert"))
@requires_role("editor")
async def cmd_revert(
    message: Message,
    command: CommandObject,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    state: FSMContext,
    **_: object,
) -> None:
    raw_args = (command.args or "").strip()
    short_sha, hard_mode = _parse_revert_args(raw_args)
    if short_sha is None:
        await message.answer("Использование: <code>/revert &lt;short_sha&gt; [--hard]</code>")
        return
    if len(short_sha) < _SHORT_SHA_MIN:
        await message.answer(f"Слишком короткий SHA. Нужен минимум {_SHORT_SHA_MIN} символов.")
        return
    if hard_mode and user.role != "admin":
        await message.answer("Hard mode доступен только admin.")
        return

    repo_path = cfg.repository.require_local_path()
    max_count = None if hard_mode else _DEFAULT_RECENT_LIMIT
    try:
        commit = git_service.find_commit_by_short_sha(
            repo_path,
            short_sha,
            cfg.repository.work_branch,
            max_count=max_count,
            marker=git_service.BOT_COMMIT_MARKER,
        )
    except GrimSproutError as exc:
        await message.answer(f"Не удалось найти коммит: <code>{html.escape(str(exc))}</code>")
        return

    commit_message = _to_text(commit.message)
    summary = commit_message.splitlines()[0].strip() if commit_message.splitlines() else commit.hexsha[:10]
    payload = {
        "action": "revert",
        "target_sha": commit.hexsha,
        "short_sha": short_sha,
        "summary": summary,
        "mode": "hard" if hard_mode else "default",
        "tg_id": user.tg_id,
    }

    preview = _build_preview(target_sha=commit.hexsha, summary=summary, hard_mode=hard_mode)
    if cfg.repository.confirm_commits:
        await state.set_state(RevertFSM.waiting)
        await state.update_data(pending_revert=payload)
        await message.answer(preview, reply_markup=_revert_confirm_keyboard())
        return

    try:
        sha = await _execute_revert(payload, cfg=cfg, db=db)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked revert: {}", exc)
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="revert_blocked",
            payload={"reason": str(exc), "target_sha": commit.hexsha},
        )
        await message.answer(
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>"
        )
        return
    except GrimSproutError as exc:
        logger.exception("revert failed")
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="revert_failed",
            payload={"error": str(exc), "target_sha": commit.hexsha},
        )
        await message.answer(f"Ритуал прерван: <code>{html.escape(str(exc))}</code>")
        return

    await message.answer(
        f"↩️ Откат выполнен.\n"
        f"Отменён: <code>{commit.hexsha[:10]}</code>\n"
        f"Коммит отката: <code>{sha[:10]}</code>"
    )


@router.callback_query(RevertFSM.waiting, F.data.in_({"revert:confirm", "revert:cancel"}))
@requires_role("editor")
async def revert_confirm_callback(
    callback: CallbackQuery,
    state: FSMContext,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    await callback.answer()

    if callback.data == "revert:cancel":
        await state.clear()
        await _safe_edit_callback_message(callback, "❌ Откат отменён.")
        return

    data = await state.get_data()
    payload = data.get("pending_revert")
    await state.clear()
    if not payload:
        await _safe_edit_callback_message(callback, "Не найдено ожидаемого отката. Запусти команду заново.")
        return

    try:
        sha = await _execute_revert(payload, cfg=cfg, db=db)
    except DirtyRepoError as exc:
        logger.warning("dirty repo blocked revert: {}", exc)
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="revert_blocked",
            payload={"reason": str(exc), "target_sha": payload.get("target_sha")},
        )
        await _safe_edit_callback_message(
            callback,
            f"🪦 Склеп в беспорядке: в репозитории есть посторонние правки.\nПодробности: <code>{exc}</code>",
        )
        return
    except GrimSproutError as exc:
        logger.exception("revert failed")
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="revert_failed",
            payload={"error": str(exc), "target_sha": payload.get("target_sha")},
        )
        await _safe_edit_callback_message(callback, f"Ритуал прерван: <code>{html.escape(str(exc))}</code>")
        return

    await _safe_edit_callback_message(
        callback,
        f"↩️ Откат выполнен.\n"
        f"Отменён: <code>{payload['target_sha'][:10]}</code>\n"
        f"Коммит отката: <code>{sha[:10]}</code>",
    )


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
