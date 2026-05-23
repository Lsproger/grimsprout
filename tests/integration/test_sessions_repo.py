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


# ---- conversation history ---------------------------------------------------


async def test_append_history_stores_turns(mongo_db) -> None:
    await sessions_repo.append_history(mongo_db, 99, "user", "как полить?")
    await sessions_repo.append_history(mongo_db, 99, "assistant", "Раз в неделю.")

    s = await sessions_repo.get(mongo_db, 99)
    assert s is not None
    assert len(s.conversation_history) == 2
    assert s.conversation_history[0].role == "user"
    assert s.conversation_history[0].content == "как полить?"
    assert s.conversation_history[1].role == "assistant"
    assert s.conversation_history[1].content == "Раз в неделю."


async def test_append_history_respects_max_items(mongo_db) -> None:
    # Fill with 6 turns but max_items=4 → only the last 4 are kept
    for i in range(6):
        await sessions_repo.append_history(mongo_db, 99, "user", f"msg{i}", max_items=4)

    s = await sessions_repo.get(mongo_db, 99)
    assert s is not None
    assert len(s.conversation_history) == 4
    assert s.conversation_history[0].content == "msg2"
    assert s.conversation_history[-1].content == "msg5"


async def test_clear_history_empties_array(mongo_db) -> None:
    await sessions_repo.append_history(mongo_db, 99, "user", "hello")
    await sessions_repo.append_history(mongo_db, 99, "assistant", "hi")
    await sessions_repo.clear_history(mongo_db, 99)

    s = await sessions_repo.get(mongo_db, 99)
    assert s is not None
    assert s.conversation_history == []


async def test_append_history_upserts_new_user(mongo_db) -> None:
    """append_history creates the session document if it doesn't exist."""
    s_before = await sessions_repo.get(mongo_db, 777)
    assert s_before is None

    await sessions_repo.append_history(mongo_db, 777, "user", "test")

    s = await sessions_repo.get(mongo_db, 777)
    assert s is not None
    assert len(s.conversation_history) == 1
