"""SessionsRepo: per-user current plant selection and conversation history."""

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


async def append_history(
    db: AsyncIOMotorDatabase,
    tg_id: int,
    role: str,
    content: str,
    max_items: int = 20,
) -> None:
    """Append a single conversation turn; keep only the last max_items entries."""
    turn = {"role": role, "content": content, "ts": datetime.now(tz=UTC)}
    await db.sessions.update_one(
        {"tg_id": tg_id},
        {
            "$push": {
                "conversation_history": {
                    "$each": [turn],
                    "$slice": -max_items,
                }
            },
            "$set": {"updated_at": datetime.now(tz=UTC)},
            "$setOnInsert": {"tg_id": tg_id},
        },
        upsert=True,
    )


async def clear_history(db: AsyncIOMotorDatabase, tg_id: int) -> None:
    """Clear conversation history for a user."""
    await db.sessions.update_one(
        {"tg_id": tg_id},
        {"$set": {"conversation_history": [], "updated_at": datetime.now(tz=UTC)}},
    )
