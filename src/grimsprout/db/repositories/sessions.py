"""SessionsRepo: per-user current plant selection."""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.models import Session


async def get(db: AsyncIOMotorDatabase, tg_id: int) -> Session | None:
    doc = await db.sessions.find_one({"tg_id": tg_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return Session(**doc)


async def set_current_plant(db: AsyncIOMotorDatabase, tg_id: int, plant_id: str | None) -> None:
    await db.sessions.update_one(
        {"tg_id": tg_id},
        {
            "$set": {"current_plant_id": plant_id, "updated_at": datetime.now(tz=UTC)},
            "$setOnInsert": {"tg_id": tg_id},
        },
        upsert=True,
    )
