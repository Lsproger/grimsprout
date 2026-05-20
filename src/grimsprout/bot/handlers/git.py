"""Git remote commands: /push, /pr.

Both are restricted to ``publisher``/``admin`` per docs/spec/07-roles-and-auth.md.
They always operate on the bot's ``work_branch``; ``git_branch`` (base) is
never written to directly.
"""

from __future__ import annotations

import os

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.config import AppConfig
from grimsprout.db.models import User
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service, github_pr
from grimsprout.services.auth_service import requires_role
from grimsprout.utils.errors import GrimSproutError

router = Router(name="git")


@router.message(Command("push"))
@requires_role("publisher", "admin")
async def cmd_push(
    message: Message,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    repo_path = cfg.repository.require_local_path()
    branch = cfg.repository.work_branch
    remote = cfg.repository.git_remote
    try:
        git_service.push(repo_path, remote, branch)
    except GrimSproutError as exc:
        logger.warning("push failed: {}", exc)
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="push_failed",
            payload={"branch": branch, "remote": remote, "error": str(exc)},
        )
        await message.answer(f"🪦 Push не удался: <code>{exc}</code>")
        return

    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="push",
        payload={"branch": branch, "remote": remote},
    )
    await message.answer(f"📤 Ветка <code>{branch}</code> отправлена в <code>{remote}</code>.")


@router.message(Command("pr"))
@requires_role("publisher", "admin")
async def cmd_pr(
    message: Message,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
    **_: object,
) -> None:
    repo_path = cfg.repository.require_local_path()
    head = cfg.repository.work_branch
    base = cfg.repository.git_branch

    # Make sure the branch is on the remote first; otherwise GitHub will
    # reject the PR with "head does not exist".
    try:
        git_service.push(repo_path, cfg.repository.git_remote, head)
    except GrimSproutError as exc:
        await message.answer(f"🪦 Push перед PR не удался: <code>{exc}</code>")
        return

    token = os.environ.get(cfg.repository.github_token_env, "").strip()
    title = f"GrimSprout: auto changes from {head}"
    body = (
        "Автоматически собранные изменения от GrimSprout.\n\n"
        f"Открыто пользователем tg_id=<code>{user.tg_id}</code>."
    )
    try:
        pr_url = github_pr.open_pr(
            configured_path=cfg.repository.path,
            repo_path=repo_path,
            token=token,
            title=title,
            body=body,
            head=head,
            base=base,
        )
    except GrimSproutError as exc:
        logger.warning("pr failed: {}", exc)
        await audit_svc.record(
            db,
            tg_id=user.tg_id,
            action="pr_failed",
            payload={"head": head, "base": base, "error": str(exc)},
        )
        await message.answer(f"🪦 PR не создан: <code>{exc}</code>")
        return

    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="pr",
        payload={"head": head, "base": base, "url": pr_url},
    )
    await message.answer(f"🔀 PR: {pr_url}")


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
