"""AuditRepo: append-only audit log."""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.models import AuditEntry


async def log(db: AsyncIOMotorDatabase, entry: AuditEntry) -> None:
    await db.audit_log.insert_one(entry.model_dump())
