"""Integration smoke tests for grimsprout.db.client (indexes)."""
from __future__ import annotations

import pytest

from grimsprout.db.client import init_indexes

pytestmark = pytest.mark.mongo


async def test_init_indexes_creates_expected_indexes(mongo_db) -> None:
    await init_indexes(mongo_db)

    users_idx = await mongo_db.users.index_information()
    assert "uniq_tg_id" in users_idx
    assert users_idx["uniq_tg_id"].get("unique") is True

    sessions_idx = await mongo_db.sessions.index_information()
    assert "uniq_tg_id" in sessions_idx

    audit_idx = await mongo_db.audit_log.index_information()
    assert "ts_desc" in audit_idx
    assert "tg_id" in audit_idx
    assert "action" in audit_idx


async def test_init_indexes_is_idempotent(mongo_db) -> None:
    await init_indexes(mongo_db)
    await init_indexes(mongo_db)  # must not raise
