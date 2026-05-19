"""Integration tests for grimsprout.db.repositories.sessions."""
from __future__ import annotations

import pytest

from grimsprout.db.repositories import sessions as sessions_repo

pytestmark = pytest.mark.mongo


async def test_get_missing_returns_none(mongo_db) -> None:
    assert await sessions_repo.get(mongo_db, 42) is None


async def test_set_and_get(mongo_db) -> None:
    await sessions_repo.set_current_plant(mongo_db, 42, "areca_01")

    s = await sessions_repo.get(mongo_db, 42)
    assert s is not None
    assert s.tg_id == 42
    assert s.current_plant_id == "areca_01"


async def test_set_overwrites(mongo_db) -> None:
    await sessions_repo.set_current_plant(mongo_db, 42, "areca_01")
    await sessions_repo.set_current_plant(mongo_db, 42, "calathea_01")

    s = await sessions_repo.get(mongo_db, 42)
    assert s is not None
    assert s.current_plant_id == "calathea_01"


async def test_set_clears_to_none(mongo_db) -> None:
    await sessions_repo.set_current_plant(mongo_db, 42, "areca_01")
    await sessions_repo.set_current_plant(mongo_db, 42, None)

    s = await sessions_repo.get(mongo_db, 42)
    assert s is not None
    assert s.current_plant_id is None


async def test_updated_at_is_refreshed(mongo_db) -> None:
    import asyncio

    await sessions_repo.set_current_plant(mongo_db, 42, "areca_01")
    first = await sessions_repo.get(mongo_db, 42)
    assert first is not None

    await asyncio.sleep(0.01)
    await sessions_repo.set_current_plant(mongo_db, 42, "calathea_01")
    second = await sessions_repo.get(mongo_db, 42)
    assert second is not None
    assert second.updated_at >= first.updated_at
