"""Audit helper: convenience wrapper over repositories.audit."""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.models import AuditEntry
from grimsprout.db.repositories import audit as audit_repo


async def record(
    db: AsyncIOMotorDatabase,
    *,
    tg_id: int,
    action: str,
    payload: dict | None = None,
    file: str | None = None,
    commit_sha: str | None = None,
) -> None:
    await audit_repo.log(
        db,
        AuditEntry(
            tg_id=tg_id,
            action=action,
            payload=payload or {},
            file=file,
            commit_sha=commit_sha,
        ),
    )
