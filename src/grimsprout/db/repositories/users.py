"""UsersRepo: CRUD over `users` collection."""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.db.models import Role, User


async def get_by_tg_id(db: AsyncIOMotorDatabase, tg_id: int) -> User | None:
    doc = await db.users.find_one({"tg_id": tg_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return User(**doc)


async def upsert(db: AsyncIOMotorDatabase, user: User) -> None:
    data = user.model_dump()
    tg_id = data.pop("tg_id")
    await db.users.update_one(
        {"tg_id": tg_id},
        {"$set": data, "$setOnInsert": {"tg_id": tg_id}},
        upsert=True,
    )


async def set_role(db: AsyncIOMotorDatabase, tg_id: int, role: Role) -> bool:
    res = await db.users.update_one({"tg_id": tg_id}, {"$set": {"role": role}})
    return res.matched_count > 0


async def list_all(db: AsyncIOMotorDatabase) -> list[User]:
    out: list[User] = []
    async for doc in db.users.find({}).sort("added_at", 1):
        doc.pop("_id", None)
        out.append(User(**doc))
    return out


async def find_first_admin(db: AsyncIOMotorDatabase) -> User | None:
    doc = await db.users.find_one({"role": "admin"})
    if not doc:
        return None
    doc.pop("_id", None)
    return User(**doc)


async def ensure_bootstrap_admin(db: AsyncIOMotorDatabase, tg_id: int) -> bool:
    """Create the bootstrap admin if no document with this tg_id exists. Returns True if inserted."""
    existing = await db.users.find_one({"tg_id": tg_id})
    if existing:
        return False
    await db.users.insert_one(
        User(
            tg_id=tg_id,
            role="admin",
            display_name="bootstrap-admin",
            added_by=None,
            added_at=datetime.now(tz=UTC),
        ).model_dump()
    )
    return True
