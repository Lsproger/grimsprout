"""Motor client factory + indexes init."""

from __future__ import annotations

import os
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from grimsprout.config import load_config


@lru_cache(maxsize=1)
def get_client() -> AsyncIOMotorClient:
    cfg = load_config()
    uri = os.environ.get(cfg.mongo.uri_env)
    if not uri:
        raise RuntimeError(f"MongoDB URI not set (env var: {cfg.mongo.uri_env})")
    return AsyncIOMotorClient(uri)


def get_db() -> AsyncIOMotorDatabase:
    cfg = load_config()
    return get_client()[cfg.mongo.database]


async def init_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index([("tg_id", ASCENDING)], unique=True, name="uniq_tg_id")
    await db.sessions.create_index([("tg_id", ASCENDING)], unique=True, name="uniq_tg_id")
    await db.audit_log.create_index([("ts", DESCENDING)], name="ts_desc")
    await db.audit_log.create_index([("tg_id", ASCENDING)], name="tg_id")
    await db.audit_log.create_index([("action", ASCENDING)], name="action")
