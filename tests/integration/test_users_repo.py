"""Integration tests for grimsprout.db.repositories.users."""
from __future__ import annotations

import pytest

from grimsprout.db.client import init_indexes
from grimsprout.db.models import User
from grimsprout.db.repositories import users as users_repo

pytestmark = pytest.mark.mongo


async def test_upsert_and_get(mongo_db) -> None:
    user = User(tg_id=42, role="editor", display_name="Yura")
    await users_repo.upsert(mongo_db, user)

    got = await users_repo.get_by_tg_id(mongo_db, 42)
    assert got is not None
    assert got.tg_id == 42
    assert got.role == "editor"
    assert got.display_name == "Yura"


async def test_get_missing_returns_none(mongo_db) -> None:
    assert await users_repo.get_by_tg_id(mongo_db, 999_999) is None


async def test_upsert_is_idempotent(mongo_db) -> None:
    user = User(tg_id=42, role="viewer")
    await users_repo.upsert(mongo_db, user)
    await users_repo.upsert(mongo_db, user)

    all_users = await users_repo.list_all(mongo_db)
    assert sum(1 for u in all_users if u.tg_id == 42) == 1


async def test_upsert_updates_existing(mongo_db) -> None:
    await users_repo.upsert(mongo_db, User(tg_id=42, role="viewer"))
    await users_repo.upsert(mongo_db, User(tg_id=42, role="admin", display_name="boss"))

    got = await users_repo.get_by_tg_id(mongo_db, 42)
    assert got is not None
    assert got.role == "admin"
    assert got.display_name == "boss"


async def test_set_role(mongo_db) -> None:
    await users_repo.upsert(mongo_db, User(tg_id=42, role="viewer"))
    assert await users_repo.set_role(mongo_db, 42, "editor") is True

    got = await users_repo.get_by_tg_id(mongo_db, 42)
    assert got is not None and got.role == "editor"


async def test_set_role_missing_user(mongo_db) -> None:
    assert await users_repo.set_role(mongo_db, 999, "admin") is False


async def test_list_all_orders_by_added_at(mongo_db) -> None:
    from datetime import datetime, timedelta

    base = datetime.utcnow()
    await users_repo.upsert(
        mongo_db, User(tg_id=2, role="viewer", added_at=base + timedelta(seconds=2))
    )
    await users_repo.upsert(
        mongo_db, User(tg_id=1, role="viewer", added_at=base + timedelta(seconds=1))
    )

    listed = await users_repo.list_all(mongo_db)
    tg_ids = [u.tg_id for u in listed]
    assert tg_ids == [1, 2]


async def test_find_first_admin(mongo_db) -> None:
    assert await users_repo.find_first_admin(mongo_db) is None
    await users_repo.upsert(mongo_db, User(tg_id=1, role="editor"))
    assert await users_repo.find_first_admin(mongo_db) is None

    await users_repo.upsert(mongo_db, User(tg_id=2, role="admin"))
    admin = await users_repo.find_first_admin(mongo_db)
    assert admin is not None and admin.tg_id == 2


async def test_ensure_bootstrap_admin_creates_once(mongo_db) -> None:
    assert await users_repo.ensure_bootstrap_admin(mongo_db, 42) is True
    assert await users_repo.ensure_bootstrap_admin(mongo_db, 42) is False

    got = await users_repo.get_by_tg_id(mongo_db, 42)
    assert got is not None and got.role == "admin"


async def test_unique_tg_id_index(mongo_db) -> None:
    from pymongo.errors import DuplicateKeyError

    await init_indexes(mongo_db)
    await mongo_db.users.insert_one({"tg_id": 7, "role": "viewer"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.users.insert_one({"tg_id": 7, "role": "viewer"})
